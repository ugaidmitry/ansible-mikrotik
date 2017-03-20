#!/usr/bin/env python
# coding: utf-8
"""MikroTik RouterOS ansible facts gathering module"""

import socket
from mikrotik_ansible import *

DOCUMENTATION = """
---

module: mikrotik_facts
short_description: Gather facts from MikroTik RouterOS devices
description:
    - Gather fact data (characteristics) of MikroTik RouterOS devices.
    - If you create router user 'ansible' with ssh-key you can omit username/password in playbooks    
return_data:
    - identity
    - license
    - resources
    - routerboard
    - health
    - users
    - packages
    - interfaces
    - ip addresses
    - mac addresses
    - misc info
options:
    verbose:
        description:
            - Gather even more device facts (slower)
        required: no
        default: false
    port:
        description:
            - SSH listening port of the MikroTik device
        required: no
        default: 22
    hostname:
        description:
            - IP Address or hostname of the MikroTik device
        required: yes
        default: null
    username:
        description:
            - Username used to login to the device
        required: no
        default: ansible
    password:
        description:
            - Password used to login to the device
        required: no
        default: null

"""
EXAMPLES = """

- name: Gather MikroTik facts
    mikrotik_facts:
        hostname: "{{ inventory_hostname }}"
        username: admin

"""
RETURN = """

ansible_facts:
    description: Returns facts collected from the device
    returned: always
    type: dict

"""
SHELL_USAGE = """

mikrotik_facts.py --shellmode --hostname=<hostname> [--verbose] [--port=<port>]
                 [--username=<username>] [--password=<password>]

"""

try:
    import paramiko
except ImportError as import_error:
    HAS_SSHCLIENT = False

try:
    from ansible.module_utils.basic import AnsibleModule
except ImportError:
    SHELLMODE = True

def main():
    rosdev = {}
    cmd_timeout = 15
    changed = False
    if not SHELLMODE:
        module = AnsibleModule(
            argument_spec=dict(
                verbose=dict(default=False, type='bool'),
                port=dict(default=22, type='int'),
                timeout=dict(default=30, type='float'),
                hostname=dict(required=True),
                username=dict(default='ansible', type='str'),
                password=dict(default=None, type='str'),
            ), supports_check_mode=False
        )
        if not HAS_SSHCLIENT:
            safe_fail(module, msg='There was a problem loading module: ',
                      error=str(import_error))

        verbose = module.params['verbose']
        rosdev['hostname'] = socket.gethostbyname(module.params['hostname'])
        rosdev['username'] = module.params['username']
        rosdev['password'] = module.params['password']
        rosdev['port'] = module.params['port']
        rosdev['timeout'] = module.params['timeout']

    elif len(sys.argv) > 1 and 'help' not in SHELLOPTS:
        if not HAS_SSHCLIENT:
            sys.exit("SSH client error: " + str(import_error))
        rosdev['hostname'] = socket.gethostbyname(SHELLOPTS['hostname'])
        rosdev['username'] = SHELLOPTS['username']
        rosdev['password'] = SHELLOPTS['password']
        rosdev['port'] = SHELLOPTS['port']
        rosdev['timeout'] = SHELLOPTS['timeout']
        verbose = False
        module = None
        if 'verbose' in SHELLOPTS:
            verbose = SHELLOPTS['verbose']
    else:
        print "Ansible MikroTik Library %s" % MIKROTIK_MODULES
        sys.exit(SHELL_USAGE)

    device = paramiko.SSHClient()
    device.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    device_connect(module, device, rosdev)
    mtfacts = {}
    mgmt = None

    identity = sshcmd(module, device, cmd_timeout, "system identity print")
    mtfacts['identity'] = str(identity.split(": ")[1])
    user_ssh_keys = parse_terse(device, "key-owner",
            "user ssh-keys print terse where user=" + rosdev['username'])
    if len(user_ssh_keys):
        mtfacts['user_ssh_keys'] = user_ssh_keys
    src = parse_terse(device, "address",
            'user active print terse where name="' + rosdev['username'] + '" and via=ssh')
    if len(src) == 1:
        mtfacts['ansible_source_ip'] = src[0]
        con = parse_terse(device, "dst-address",
            'ip firewall connection print terse where tcp-state=established and '
            + 'src-address~"' + src[0] + '" and dst-address~".*:' + str(rosdev['port'])
            + '"')
        if len(con) == 1:
            ifc = parse_terse(device, "interface",
                'ip address print terse where address~"' + str(con[0]).split(":")[0] + '"')
        else:
            ifc = parse_terse(device, "interface",
                'ip address print terse where address~"' + rosdev['hostname'] + '"')
        if len(ifc) == 1:
            mgmt = str(ifc[0])

    mtfacts = parse_facts(device, mtfacts, "system resource print without-paging")
    mtfacts = parse_facts(device, mtfacts, "system routerboard print without-paging")
    mtfacts = parse_facts(device, mtfacts, "system health print without-paging")
    mtfacts = parse_facts(device, mtfacts, "system license print without-paging")
    mtfacts = parse_facts(device, mtfacts, "ip cloud print without-paging", "cloud_")
    #mtfacts['routeros_version'] = mtfacts['version'].split(" ")[0]

    mtfacts['enabled_packages'] = parse_terse(device, "name",
            "system package print terse without-paging where disabled=no")
    for pkg in mtfacts['enabled_packages']:
        if 'routeros' in pkg:
            mtfacts['enabled_packages'].remove(pkg)
    mtfacts['enabled_interfaces'] = parse_terse(device, "name",
            "interface print terse without-paging where disabled=no")
    if mgmt and mgmt in mtfacts['enabled_interfaces']:
        mtfacts['management_interface'] = mgmt
    mtfacts['ip_addresses'] = parse_terse(device, "address",
            "ip address print terse without-paging where disabled=no")
    mtfacts['mac_addresses'] = parse_terse(device, "mac-address",
            "interface print terse without-paging where disabled=no")
    mtfacts['remote_syslog'] = parse_terse(device, "remote",
            "system logging action print terse without-paging")
    mtfacts['email_server'] = parse_terse(device, "address",
            "tool e-mail export hide-sensitive")
    if 'wireless' in mtfacts['enabled_packages']:
        wifaces = parse_terse(device, "name",
                "interface wireless print terse without-paging")
        if wifaces:
            mtfacts['wireless_interfaces'] = wifaces
    if 'ipv6' in mtfacts['enabled_packages']:
        mtfacts['ipv6_addresses'] = parse_terse(device, "address",
                "ipv6 address print terse without-paging where disabled=no")

    if verbose:
        mtfacts = parse_facts(device, mtfacts, "ip ssh print without-paging", "ssh_")
        mtfacts = parse_facts(device, mtfacts, "ip settings print without-paging", "ipv4_")
        mtfacts = parse_facts(device, mtfacts, "system clock print without-paging", "clock_")
        mtfacts = parse_facts(device, mtfacts, "snmp print without-paging", "snmp_")
        mtfacts['disabled_packages'] = parse_terse(device, "name",
            "system package print terse without-paging where disabled=yes")
        mtfacts['disabled_interfaces'] = parse_terse(device, "name",
            "interface print terse without-paging where disabled=yes")
        mtfacts = parse_facts(device, mtfacts,
            "interface bridge settings print without-paging", "bridge_")
        mtfacts = parse_facts(device, mtfacts,
            "ip firewall connection tracking print without-paging", "conntrack_")
        mtfacts['users'] = parse_terse(device, "name",
            "user print terse without-paging where disabled=no")
        mtfacts['mac_server_interfaces'] = parse_terse(device, "interface",
            "tool mac-server print terse without-paging where disabled=no")
        mtfacts['mac_winbox_interfaces'] = parse_terse(device, "interface",
            "tool mac-server mac-winbox print terse without-paging where disabled=no")
        mtfacts['ip_services'] = parse_terse(device, "name",
            "ip service print terse without-paging where disabled=no")
        mtfacts['neighbor_discovery_interfaces'] = parse_terse(device, "name",
            "ip neighbor discovery print terse without-paging where disabled=no")
        mtfacts['ethernet_interfaces'] = parse_terse(device, "name",
            "interface ethernet print terse without-paging")
        mtfacts['ethernet_switch_types'] = parse_terse(device, "type",
            "interface ethernet switch print terse without-paging")
        mtfacts['bridge_interfaces'] = parse_terse(device, "name",
            "interface bridge print terse without-paging")
        mtfacts = parse_facts(device, mtfacts,
            "system ntp client print without-paging", "ntp_client_")
        if 'ntp' in mtfacts['enabled_packages']:
            mtfacts = parse_facts(device, mtfacts,
                "system ntp server print without-paging", "ntp_server_")
        if 'ipv6' in mtfacts['enabled_packages']:
            mtfacts = parse_facts(device, mtfacts, "ipv6 settings print without-paging",
                "ipv6_")

    if SHELLMODE:
        device.close()
        for fact in sorted(mtfacts):
            if isinstance(mtfacts[fact], list):
                print "%s: %s" % (fact, ', '.join(mtfacts[fact]))
            else:
                print "%s: %s" % (fact, mtfacts[fact])
        sys.exit(0)

    safe_exit(module, device, ansible_facts=mtfacts, changed=changed)


if __name__ == '__main__':
    SHELLOPTS = parse_opts(sys.argv)
    if 'shellmode' in SHELLOPTS:
        SHELLMODE = True
    main()