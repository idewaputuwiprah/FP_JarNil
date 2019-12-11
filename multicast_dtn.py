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
name = ""
expired = False
sending = False


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


def calculateDist(msg_loc):
    global latitude, longitude
    myloc = (latitude, longitude)
    dis = distance.distance(msg_loc, myloc).meters
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
            continue
        global now
        global expired
        while msg:
            nextt = time_pc()
            dif = nextt - now
            minutes = dif.seconds / 60
            # print(minutes)
            if minutes >= 1.0:
                print("the message is expired")
                expired = True
                msg = {}

def send_loop(multicast_ip, port):
    my_socket = connect_socket(multicast_ip, port)
    global expired
    
    while True:
        global msg
        global sending
        sending = False
        while not sending:
            continue
        while not expired:
            temp = pickle.dumps(msg)
            my_socket.sendto(temp, (multicast_ip, port))
        if expired:
            print("destroying this thread...")
            break

def listen_loop(multicast_ip, port):
    my_socket = create_socket(multicast_ip, port)

    global msg
    global now
    global name
    global sending

    while True:
        while sending:
            continue
        
        if expired:
            break
            # Data waits on socket buffer until we retrieve it.
            # NOTE: Normally, you would want to compare the incoming data's source address to your own, and filter it out
            #       if it came rom the current machine. Everything you send gets echoed back at you if your socket is
            #       subscribed to the multicast group.
        data, address = my_socket.recvfrom(4096)
        msg = pickle.loads(data)
        now = msg["time"]
        msg_loc = (msg["lat"], msg["long"])
        dist = calculateDist(msg_loc)
        msg["hop"] += 1

        if msg["sender"] != name:
            if dist < 500:
                if int(msg["hop"]) < 4:
                    if str(msg["des"]) == name:
                        print("< %s > says '%s'" % (msg["sender"], msg["message"]))
                    else:
                        print("You got message, but it's not for you :)")
                else:
                    print("message exceed max_hop")
                    msg = {}
            else:
                print("The dist is too far")
                msg = {}
            
            sending = True

def announce_loop(multicast_ip, port):
    # Offset the port by one so that we can send and receive on the same machine
    my_socket = connect_socket(multicast_ip, port)
    global msg
    global name
    global now
    global latitude, longitude
    

    # NOTE: Announcing every second, as this loop does, is WAY aggressive. 30 - 60 seconds is usually
    #       plenty frequent for most purposes.
    while True:
        now = time_pc()
        # Just sending Unix time as a message
        if not msg:
            message = {}
            message["sender"] = name
            message["message"] = input("Enter your message: ")
            message["des"] = input("Enter your destination: ")
            message["hop"] = 0
            message["long"] = longitude
            message["lat"] = latitude
            message["time"] = now

        # Send data. Destination must be a tuple containing the ip and port.
        temp = pickle.dumps(message)
        my_socket.sendto(temp, (multicast_ip, port))
        # time.sleep(1)
        break

def init_listen():
    # print("success created")
    while True:
        while not expired:
            continue
        exit("message already expired")

if __name__ == '__main__':
    # Choose an arbitrary multicast IP and port.
    # 239.255.0.0 - 239.255.255.255 are for local network multicast use.
    # Remember, you subscribe to a multicast IP, not a port. All data from all ports
    # sent to that multicast IP will be echoed to any subscribed machine.
    multicast_address = "224.0.0.1"
    multicast_port = 10000

    name = input("Enter your name: ")

    geolocator = Nominatim(user_agent="specify_your_app_name_here")
    location = input("Enter your location: ")
    loc = geolocator.geocode(location)

    longitude = loc.longitude
    latitude = loc.latitude

    init_awal = threading.Thread(target=init_listen)
    init_awal.daemon = True
    init_awal.start()

    time_now = threading.Thread(target=time_msg)
    time_now.daemon = True
    time_now.start()

    receive = threading.Thread(target=listen_loop,args=(multicast_address,multicast_port))
    receive.daemon = True
    receive.start()

    send = threading.Thread(target=send_loop,args=(multicast_address,multicast_port))
    send.daemon = True
    send.start()


    while True:

        print("1.Announce")
        print("2.Exit")
        c = input("~")

    # When launching this example, you can choose to put it in listen or announce mode.
    # Announcing doesn't require binding to a port, but we do it here just to reuse code.
    # It binds to the requested port + 1, allowing you to run the announce and listen modes
    # on the same machine at the same time.

    # In a real case, you'll most likely send and receive from the same port using Gevent or Twisted,
    # so the code in create_socket() will apply more directly.

        if int(c) == 1:
            announce_loop(multicast_address, multicast_port)
        else:
            exit("Run 'multicast_example.py listen' or 'multicast_example.py announce'.")
