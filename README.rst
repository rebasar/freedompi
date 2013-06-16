Freedom Pi - Anonymizer Setup Helper
####################################

What is it?
===========

FreedomPi is simply a python script to help you convert a
Debian/Raspbian system to an anonymizing wireless access point. While
it is usable on any kind of Debian based system, it has been developed
and intended to be used on a Raspberry Pi.

How to install/use?
===================

The first and most important part is to have a computer with two
network interfaces. At least one of those interfaces MUST be wireless
and have the capability to act as an access point. I cannot tell you
which hardware supports it and which don't, because I have no
idea. You might have some idea from `hostapd website
<http://hostap.epitest.fi/hostapd/>`_.

As a prerequisite, make sure that you have these packages installed:
python, iptables, udhcpd, hostapd, tor.

Make sure that your /etc/network/interfaces file does not contain any
configuration about your wireless interface.

Download the freedompi.py and freedompi_config.py files. Edit the file
freedompi_config.py to fit your needs.

Then run: sudo python freedompi.py

This will install the configuration to /boot/freedompi_config.py (for the sake of easy configuration on Raspberry Pi, I know it is not compliant with any sane directory structure standard), the freedompi script to /usr/sbin an init script to /etc/init.d/freedompi and enable it to run on boot. It will also update the network, udhcpd, hostapd and tor configurations to setup the anonymizing system and insert some iptables rules.

Now reboot and your wireless access point should be up and running.

Have fun!
