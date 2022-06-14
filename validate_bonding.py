#!/usr/bin/python

"""
This script was written to find out if a linux server is configured with
network bonding, and the bonding is in active-backup mode. It also checks
that both NIC cards(script only allows 2 NICs) are UP and are connected
to same VLAN ID. Finally it displays a summary NIC bonding configuration
in json format. 

-------------
Example output:

{
    "bond0": {
        "ens3f0": {
            "status": "up",
            "vlanid": "200"
        },
        "eno49": {
            "status": "up",
            "vlanid": "200"
        }
    },
    "bond1": {
        "ens3f1": {
            "status": "down",
            "vlanid": "300"
        },
        "eno50": {
            "status": "up",
            "vlanid": "300"
        }
    }
}
----------------

This script will be helpful few you need to verify that bonding is healthy
on a bunch of servers in cases like a set of network switches are undergoing
maintenance and thus admins need to verify that server can still serve traffic
via standby NIC of the bond.

For running it on multiple servers, we can make use of tools like Ansible

"""

import os, subprocess, re, json

def run_command(cmd):
    result = []
    process = subprocess.Popen(cmd, shell=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE)
    return_code = process.wait()
    output = process.stdout.readlines()
    for o in output:
        result.append(o.split('\n')[0])
    return result

def get_bonds():
    bonds = []
    bonds = os.listdir("/proc/net/bonding")
    return bonds

def check_nic_status(bond):
    nic_status = dict()  # dictionary of nic:status pairs

    with open("/proc/net/bonding/" + bond) as fh:
         for line in fh:
             if re.search("Slave Interface: (.*)", line):
                nic = line.split(':')[1].strip()
                status = fh.next()
                status = status.split(':')[1].strip()
                nic_status[nic] = status

    return nic_status

def get_vlan(nic):
    vlanid = ""
    tcpdump_cmd = "/usr/bin/timeout 60 /usr/sbin/tcpdump -nn -v -s 1500 -c 1 -i "
    cdp_filter  = " 'ether[20:2] == 0x2000 and ether dst 01:00:0c:cc:cc:cc'"
    lldp_filter = " 'ether[12:2] = 0x88cc'"

    vlanid_line = run_command(tcpdump_cmd + nic + cdp_filter + "| grep 'VLAN ID'")
    if vlanid_line:
        vlanid = vlanid_line[0].split(':')[-1].strip()

    if not vlanid_line or vlanid == '1':         # checking for LLDP packets if CDP packets not received
        vlanid_line = run_command(tcpdump_cmd + nic + lldp_filter + "|grep 'vlan id'")

    """   break the output line like below captured in variable 'vlanid_line'
          'Native VLAN ID (0x0a), value length: 2 bytes: 123'
                            or
          'port vlan id (PVID): 12'
          and get the vlan ID in the last field """

    if vlanid_line:
        vlanid = vlanid_line[0].split(':')[-1].strip()

    return vlanid

def get_bonding_mode(bond):
    tmp = []
    mode = ""
    tmp = run_command("egrep '^Bonding Mode' /proc/net/bonding/bond0 | awk -F ':' '{print $2}'")
    mode = tmp[0].strip()   # list to string conversion
    
    return mode

def main():
    nic_down = "no"
    mode = ""
    nic_status = dict()
    bond_details = dict()

    bonds = get_bonds()
    if not bonds:                 # check 1 : if bonding is configured
       print("No bonding configured")
       exit(1)

    for bond in bonds:            # check 2 : if bonding mode is 'active-backup'
        mode = get_bonding_mode(bond)
        if mode != "fault-tolerance (active-backup)":
            print("Bonding mode is not active-backup")
            exit(1)

    for bond in bonds:            # get the NIC details for all bonds configured
        bond_details[bond] = {}
        nic_status = check_nic_status(bond)
        for nic in nic_status.keys():
            bond_details[bond][nic] = {}
            bond_details[bond][nic]['status'] = nic_status[nic]

    """  To help understand the next code block better, below is how bond_details dictionary looks like currently
         {
          'bond0': {'ens3f0': {'status': 'down'}, 'eno49': {'status': 'up'}}, 
          'bond1': {'ens3f1': {'status': 'down'}, 'eno50': {'status': 'up'}}
         }
    """

    for bond in bonds:
        if len(bond_details[bond].keys()) != 2:      # check 3 :  number of interfaces are 2 in normal setup
            print("Non-Standard number of Slave interfaces in : " + bond) 
            print("Number of interfaces : ", len(bond_details[bond].keys()))
        for nic in bond_details[bond].keys():
            if  bond_details[bond][nic]['status'] == 'down':
                print("NIC " + nic + " of " + bond + " is " + bond_details[bond][nic]['status'])
                nic_down = "yes"

    if nic_down == "yes":    # exit if a NIC is down
        exit(1)

    for bond in bonds:       # fetch and output the vlanid for all the NICs
        nic_status = check_nic_status(bond)
        for nic in nic_status.keys():
            vlanid = get_vlan(nic)
            bond_details[bond][nic]['vlanid'] = vlanid
            if not vlanid:
                print("Can't find the vlan ID for " + nic)

    bond_details_json = json.dumps(bond_details, indent = 4)
    print(bond_details_json)


main()
