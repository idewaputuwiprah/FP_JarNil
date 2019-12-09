# Written by Aaron Cohen -- 1/14/2013
# Brought to you by BitTorrent, Inc.
# "We're not just two guys in a basement in Sweden." TM
#
# This work is licensed under a Creative Commons Attribution 3.0 Unported License.
# See: http://creativecommons.org/licenses/by/3.0/

import sys
import re
import socket
import time
import struct
import pickle
from geopy.geocoders import Nominatim
from geopy import distance
import datetime
import threading

msg = {}
HEADERSIZE = 10
latitude = 0
longitude = 0
now = datetime.datetime.now()

def ip_is_local(ip_string):
    """
    Uses a regex to determine if the input ip is on a local network. Returns a boolean. 
    It's safe here, but never use a regex for IP verification if from a potentially dangerous source.
    """
    combined_regex = "(^10\.)|(^172\.1[6-9]\.)|(^172\.2[0-9]\.)|(^172\.3[0-1]\.)|(^192\.168\.)"
    return re.match(combined_regex, ip_string) is not None # is not None is just a sneaky way of converting to a boolean


def get_local_ip():
    """
    Returns the first externally facing local IP address that it can find.
    Even though it's longer, this method is preferable to calling socket.gethostbyname(socket.gethostname()) as
    socket.gethostbyname() is deprecated. This also can discover multiple available IPs with minor modification.
    We excludes 127.0.0.1 if possible, because we're looking for real interfaces, not loopback.
    Some linuxes always returns 127.0.1.1, which we don't match as a local IP when checked with ip_is_local().
    We then fall back to the uglier method of connecting to another server.
    """

    # socket.getaddrinfo returns a bunch of info, so we just get the IPs it returns with this list comprehension.
    local_ips = [ x[4][0] for x in socket.getaddrinfo(socket.gethostname(), 80)
                  if ip_is_local(x[4][0]) ]

    # select the first IP, if there is one.
    local_ip = local_ips[0] if len(local_ips) > 0 else None

    # If the previous method didn't find anything, use this less desirable method that lets your OS figure out which
    # interface to use.
    if not local_ip:
        # create a standard UDP socket ( SOCK_DGRAM is UDP, SOCK_STREAM is TCP )
        temp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Open a connection to one of Google's DNS servers. Preferably change this to a server in your control.
            temp_socket.connect(('8.8.8.8', 9))
            # Get the interface used by the socket.
            local_ip = temp_socket.getsockname()[0]
        except socket.error:
            # Only return 127.0.0.1 if nothing else has been found.
            local_ip = "127.0.0.1"
        finally:
            # Always dispose of sockets when you're done!
            temp_socket.close()
    return local_ip

# def create_socket(multicast_ip, port):
#     """
#     Creates a socket, sets the necessary options on it, then binds it. The socket is then returned for use.
#     """

#     # local_ip = get_local_ip()
#     local_ip = '192.168.137.1'

#     # create a UDP socket
#     my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

#     # allow reuse of addresses
#     my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

#     # set multicast interface to local_ip
#     my_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(local_ip))

#     # Set multicast time-to-live to 2...should keep our multicast packets from escaping the local network
#     my_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)

#     # Construct a membership request...tells router what multicast group we want to subscribe to
#     membership_request = socket.inet_aton(multicast_ip) + socket.inet_aton(local_ip)

#     # Send add membership request to socket
#     # See http://www.tldp.org/HOWTO/Multicast-HOWTO-6.html for explanation of sockopts
#     my_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership_request)

#     # Bind the socket to an interface.
#     # If you bind to a specific interface on the Mac, no multicast data will arrive.
#     # If you try to bind to all interfaces on Windows, no multicast data will arrive.
#     # Hence the following.
#     if sys.platform.startswith("darwin"):
#         my_socket.bind(('0.0.0.0', port))
#     else:
#         my_socket.bind(('', port))

#     return my_socket

def connect_socket(multicast_ip, port):
    my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    my_socket.settimeout(0.2)

    ttl = struct.pack('b', 1)
    my_socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

    return my_socket

def create_socket(multicast_ip, port):
    server_address = ('', port)

    my_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    my_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    my_socket.bind(server_address)

    group = socket.inet_aton(multicast_ip)
    myreq = struct.pack('4sL', group, socket.INADDR_ANY)
    my_socket.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, myreq)

    return my_socket

def get_bound_multicast_interface(my_socket):
    """
    Returns the IP address (probably your local IP) that the socket is bound to for multicast.
    Note that this may not be the same address you bound to manually if you specified 0.0.0.0.
    This isn't used here, just a useful utility method.
    """
    response = my_socket.getsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF)
    socket.inet_ntoa(struct.pack('i', response))

def drop_multicast_membership(my_socket, multicast_ip):
    """
    Drops membership to the specified multicast group without closing the socket.
    Note that this happens automatically (done by the kernel) if the socket is closed.
    """

    local_ip = get_local_ip()

    # Must reconstruct the same request used when adding the membership initially
    membership_request = socket.inet_aton(multicast_ip) + socket.inet_aton(local_ip)

    # Leave group
    my_socket.setsockopt(socket.IPPROTO_IP, socket.IP_DROP_MEMBERSHIP, membership_request)

def calculateDist(msg_loc):
    global latitude, longitude
    myloc = (latitude,longitude)
    dis = distance.distance(msg_loc,myloc).meters
    return dis

def get_IP(my_socket):
    try: 
        host_name = socket.gethostname() 
        host_ip = socket.gethostbyname(host_name)
        return host_ip
    except: 
        print("Unable to get Hostname and IP") 
        return 0

def time_pc():
    time = datetime.datetime.now()
    return time

def time_msg():
    while True:
        global msg
        while not msg:
            pass
        global now
        while msg:
            nextt = time_pc()
            dif = nextt - now
            minutes = dif.seconds / 60
            # print(minutes)
            if minutes >= 1.0:
                print("the message is expired")
                msg = {}


def listen_loop(multicast_ip, port):
    my_socket = create_socket(multicast_ip, port)

    global msg
    global now

    while True:
            # Data waits on socket buffer until we retrieve it.
            # NOTE: Normally, you would want to compare the incoming data's source address to your own, and filter it out
            #       if it came rom the current machine. Everything you send gets echoed back at you if your socket is
            #       subscribed to the multicast group.
            data, address = my_socket.recvfrom(4096)
            msg = pickle.loads(data)
            now = time_pc()
            msg_loc = (msg["lat"],msg["long"])
            dist = calculateDist(msg_loc)
            msg["hop"] += 1
            your_ip = get_IP(my_socket)

            if dist < 500:
                if int(msg["hop"]) < 4:
                    if str(msg["des"]) == your_ip:
                        print ("< %s > says '%s'" % (msg["sender"], msg["message"]))
                    else:
                        print("You got message, but it's not for you :)")
                else:
                    print("message exceed max_hop")
                    msg.clear()
            else:
                print("The dist is too far")
                msg.clear()
            break

def announce_loop(multicast_ip, port):
    # Offset the port by one so that we can send and receive on the same machine
    my_socket = connect_socket(multicast_ip, port)
    global msg
    global latitude, longitude
    your_ip = get_IP(my_socket)

    # NOTE: Announcing every second, as this loop does, is WAY aggressive. 30 - 60 seconds is usually
    #       plenty frequent for most purposes.
    while True:
        # Just sending Unix time as a message
        if not msg:
            message = {}
            message["sender"] = your_ip
            message["message"] = input("Enter your message: ")
            message["des"] = input("Enter your destination: ")
            message["hop"] = 0
            message["long"] = longitude
            message["lat"] = latitude
        else:
            message = msg

        # Send data. Destination must be a tuple containing the ip and port.
        temp = pickle.dumps(message)
        my_socket.sendto(temp, (multicast_ip, port))
        # time.sleep(1)
        break

if __name__ == '__main__':
    # Choose an arbitrary multicast IP and port.
    # 239.255.0.0 - 239.255.255.255 are for local network multicast use.
    # Remember, you subscribe to a multicast IP, not a port. All data from all ports
    # sent to that multicast IP will be echoed to any subscribed machine.
    multicast_address = "224.0.0.1"
    multicast_port = 10000

    time_now = threading.Thread(target=time_msg)
    time_now.daemon = True
    time_now.start()

    geolocator = Nominatim(user_agent="specify_your_app_name_here")
    location = input("Enter your location: ")
    loc = geolocator.geocode(location)

    longitude = loc.longitude
    latitude = loc.latitude

    while True:
        print("1.Listen")
        print("2.Announce")
        print("3.Exit")
        c = input("~")

    # When launching this example, you can choose to put it in listen or announce mode.
    # Announcing doesn't require binding to a port, but we do it here just to reuse code.
    # It binds to the requested port + 1, allowing you to run the announce and listen modes
    # on the same machine at the same time.

    # In a real case, you'll most likely send and receive from the same port using Gevent or Twisted,
    # so the code in create_socket() will apply more directly.

        if int(c) == 1:
            listen_loop(multicast_address, multicast_port)
        elif int(c) == 2:
            announce_loop(multicast_address, multicast_port)
        else:
            exit("Run 'multicast_example.py listen' or 'multicast_example.py announce'.")