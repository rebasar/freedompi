#!/usr/bin/python
#-*- coding: utf-8 -*-

import os, sys, re, stat, shutil

CONFIG_DIR = '/boot'
sys.path.append(CONFIG_DIR)

import freedompi_config as config

DAEMON_FILE_NAME = '/usr/sbin/freedompi'
CONFIG_FILE_NAME = 'freedompi_config.py'

INTERFACES_FILE = '/etc/network/interfaces'
HOSTAPD_CONFIG = '/etc/hostapd/freedompi.conf'
UDHCPD_CONFIG = '/etc/udhcpd.conf'
UDHCPD_DEFAULTS = '/etc/default/udhcpd'
UDHCPD_LEASES_FILE = '/var/lib/misc/udhcpd.leases'
TORRC = '/etc/tor/torrc'
INIT_SCRIPT_FILENAME = '/etc/init.d/freedompi'

CONFIG_START_MARKER = '### FreedomPi Configuration Start ###'
CONFIG_END_MARKER = '### FreedomPi Configuration End ###'

INTERFACES_TEMPLATE="""%(activation_line)s
iface %(interface)s inet static
  address %(address)s
  netmask %(netmask)s
  hostapd %(hostapd_config)s
"""

HOSTAPD_TEMPLATE = """
ssid=%(ssid)s
interface=%(interface)s
driver=%(driver)s
channel=%(channel)s
hw_mode=g
ieee80211n=%(ieee80211n)s
wmm_enabled=%(wmm_enabled)s
"""
HOSTAPD_WPA_TEMPLATE = """
wpa=2
wpa_passphrase=%(wpa_passphrase)s
wpa_key_mgmt=WPA-PSK
wpa_pairwise=CCMP
"""

UDHCPD_TEMPLATE = """
start		%(start)s
end		%(end)s
interface	%(interface)s
opt	dns	%(router)s
opt	router	%(router)s
option	domain	freedompi
option	subnet	%(subnet)s
option	lease	1800
"""

TORRC_TEMPLATE = """
VirtualAddrNetwork 10.192.0.0/10
AutomapHostsOnResolve 1
TransPort %(ap_ip)s:9040
DNSPort %(ap_ip)s:53
"""

INIT_SCRIPT_TEMPLATE = """#!/bin/sh

### BEGIN INIT INFO
# Provides:		freedompi
# Required-Start:	$remote_fs
# Required-Stop:	$remote_fs
# Should-Start:		$network
# Should-Stop:
# X-Start-Before:      	hostapd udhcpd tor
# Default-Start:	2 3 4 5
# Default-Stop:		0 1 6
# Short-Description:	FreedomPi Anonymous Access Point
# Description:		FreedomPi Configuration and initialization daemon
### END INIT INFO

PATH=/sbin:/bin:/usr/sbin:/usr/bin
DAEMON_SBIN=/usr/sbin/freedompi
DAEMON_DEFS=/etc/default/freedompi
NAME=freedompi
DESC="FreedomPi Anonymous Access Point"
PIDFILE=/var/run/hostapd.pid

[ -x "$DAEMON_SBIN" ] || exit 0
[ -s "$DAEMON_DEFS" ] && . $DAEMON_DEFS


. /lib/lsb/init-functions

case "$1" in
  start)
	log_daemon_msg "Starting $DESC" "$NAME"
	$DAEMON_SBIN
	log_end_msg "$?"
	;;
  stop)
	log_daemon_msg "Stopping $DESC" "$NAME"
	$DAEMON_SBIN
	log_end_msg "$?"
	;;
  reload)
  	log_daemon_msg "Reloading $DESC" "$NAME"
	$DAEMON_SBIN
	log_end_msg "$?"
	;;
  restart|force-reload)
  	$0 stop
	sleep 8
	$0 start
	;;
  status)
	status_of_proc "$DAEMON_SBIN" "$NAME"
	exit $?
	;;
  *)
	N=/etc/init.d/$NAME
	echo "Usage: $N {start|stop|restart|force-reload|reload|status}" >&2
	exit 1
	;;
esac

exit 0

"""

IPTABLES_COMMANDS = ['iptables -F',
                     'iptables -t nat -F',
                     'iptables -t nat -A PREROUTING -i %(ap_interface)s -p udp --dport 53 -j REDIRECT --to-ports 53',
                     'iptables -t nat -A PREROUTING -i %(ap_interface)s -p tcp --dport 53 -j REDIRECT --to-ports 53',
                     'iptables -t nat -A PREROUTING -i %(ap_interface)s -p tcp --syn -j REDIRECT --to-ports 9040']

def generate_interfaces_config():
    cfg = {'address':config.ap_ip,
           'interface':config.ap_interface,
           'netmask':config.ip_netmask,
           'hostapd_config':HOSTAPD_CONFIG}
    if(config.ap_interface_hotplug):
        cfg['activation_line'] = 'allow-hotplug %s'%config.ap_interface
    else:
        cfg['activation_line'] = 'auto %s'%config.ap_interface
    return INTERFACES_TEMPLATE%cfg

def generate_hostapd_config():
    ieee80211n = 1 if config.ap_80211n else 0
    base_cfg = {'ssid':config.wireless_ssid,
                'interface':config.ap_interface,
                'driver':config.ap_driver,
                'channel':config.wireless_channel,
                'ieee80211n':ieee80211n,
                'wmm_enabled':ieee80211n}
    wpa_cfg = {'wpa_passphrase':config.wireless_passphrase}
    cfg = HOSTAPD_TEMPLATE%base_cfg
    if config.wireless_passphrase:
        cfg += HOSTAPD_WPA_TEMPLATE%wpa_cfg
    return cfg

def generate_udhcpd_config():
    cfg = {'start':config.ip_range_start,
           'end':config.ip_range_end,
           'interface':config.ap_interface,
           'subnet':config.ip_netmask,
           'router':config.ap_ip}
    return UDHCPD_TEMPLATE%cfg

def generate_torrc():
    return TORRC_TEMPLATE%{'ap_ip':config.ap_ip}

def update_config_file(config_file_name, content):
    config_file = open(config_file_name, 'r')
    in_dynamic_section = False
    config_written = False
    lines = ""
    for line in config_file:
        if(not in_dynamic_section):
            lines +=  line
        if(line.strip() == CONFIG_START_MARKER):
            in_dynamic_section = True
            lines += content
            config_written = True
        if(line.strip() == CONFIG_END_MARKER and config_written == False):
            raise Exception('Found an end marker before a start marker. Please fix your "%s" file.'%config_file_name)
        if(line.strip() == CONFIG_END_MARKER):
            in_dynamic_section = False
            lines += line
    if config_written == False:
        # No config part found, appending to end
        lines += '%s\n%s\n%s\n'%(CONFIG_START_MARKER, content, CONFIG_END_MARKER)
    config_file.close()

    config_file = open(config_file_name, 'w')
    config_file.write(lines)
    config_file.flush()
    config_file.close()

def empty_config_file(fn, comment_prefix="# "):
    def add_comment_prefix(line):
        if line.startswith(comment_prefix) or line.strip() == '':
            return line
        else:
            return (comment_prefix + line)
    def filter_freedompi_lines(lines):
        ret = []
        in_dynamic_section = False
        for line in lines:
            if line.strip() == CONFIG_START_MARKER:
                in_dynamic_section = True
            if not in_dynamic_section:
                ret.append(line)
            if line.strip() == CONFIG_END_MARKER:
                in_dynamic_section = False
        return ret
    f = open(fn, 'r')
    commented_lines = [add_comment_prefix(line) for line in filter_freedompi_lines(f.readlines())]
    f.close()
    f = open(fn, 'w')
    f.write(''.join(commented_lines))
    f.flush()
    f.close()

def touch(fn):
    if not os.path.exists(fn):
        f = open(fn, 'w')
        f.write('')
        f.close()

def check_access_and_create(fn):
    if not os.path.exists(fn):
        touch(fn)
    if not os.access(fn, os.R_OK + os.W_OK):
        errmsg = 'Cannot access "%s". Aborting. Please run this script either as root or with sudo'%fn
        raise Exception(errmsg)

def check_file_access():
    try:
        check_access_and_create(INTERFACES_FILE)
        check_access_and_create(HOSTAPD_CONFIG)
        check_access_and_create(UDHCPD_CONFIG)
        check_access_and_create(UDHCPD_DEFAULTS)
        check_access_and_create(TORRC)
    except Exception, e:
        print e
        sys.exit(1)

def update_interfaces():
    update_config_file(INTERFACES_FILE, generate_interfaces_config())

def update_hostapd_config():
    empty_config_file(HOSTAPD_CONFIG)
    update_config_file(HOSTAPD_CONFIG, generate_hostapd_config())

def update_udhcpd_config():
    empty_config_file(UDHCPD_CONFIG)
    update_config_file(UDHCPD_CONFIG, generate_udhcpd_config())

def fix_udhcpd_leases():
    if not os.path.exists(UDHCPD_LEASES_FILE):
        touch(UDHCPD_LEASES_FILE)

def enable_udhcpd():
    enable_re = re.compile('DHCPD_ENABLED="no"')
    f = open(UDHCPD_DEFAULTS, 'r')
    content = f.read()
    f.close()
    new_content = enable_re.sub('DHCPD_ENABLED="yes"', content)
    f = open(UDHCPD_DEFAULTS, 'w')
    f.write(new_content)
    f.flush()
    f.close()

def update_torrc():
    empty_config_file(TORRC)
    update_config_file(TORRC, generate_torrc())

def update_iptables():
    cfg = {'ap_interface':config.ap_interface}
    for cmd in IPTABLES_COMMANDS:
        os.system(cmd%cfg)

def install_self():
    filemode = stat.S_IRUSR + stat.S_IWUSR + stat.S_IXUSR
    filemode += stat.S_IRGRP + stat.S_IXGRP
    filemode += stat.S_IROTH + stat.S_IXOTH
    if not os.path.exists(DAEMON_FILE_NAME):
        shutil.copyfile(__file__, DAEMON_FILE_NAME)
        os.chmod(DAEMON_FILE_NAME, filemode)
    basepath = os.path.dirname(__file__)
    cfg = os.path.join(basepath, CONFIG_FILE_NAME)
    if not os.path.exists(os.path.join(CONFIG_DIR, CONFIG_FILE_NAME)):
        shutil.copyfile(cfg, os.path.join(CONFIG_DIR, CONFIG_FILE_NAME))

def install_init_script():
    filemode = stat.S_IRUSR + stat.S_IWUSR + stat.S_IXUSR
    filemode += stat.S_IRGRP + stat.S_IXGRP
    filemode += stat.S_IROTH + stat.S_IXOTH
    if not os.path.exists(INIT_SCRIPT_FILENAME):
        init_file = open(INIT_SCRIPT_FILENAME,'w')
        init_file.write(INIT_SCRIPT_TEMPLATE)
        init_file.flush()
        init_file.close()
        os.chmod(INIT_SCRIPT_FILENAME, filemode)
        os.system('update-rc.d freedompi defaults')

def display_final_message():
    print """Congratulations!
Installation is finished!

Now reboot your system for the changes to take effect.
"""


def main():
    check_file_access()
    update_interfaces()
    update_hostapd_config()
    update_udhcpd_config()
    enable_udhcpd()
    fix_udhcpd_leases()
    update_torrc()
    update_iptables()
    install_self()
    install_init_script()
    # display_final_message()

if __name__ == '__main__':
    main()
