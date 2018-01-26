#!/usr/bin/env python
import serial
import time
import json
import sys
import os
import urllib

master="192.168.0.182"
port  =8010

urlroot = "http://%s:%d/api/v2" % (master, port)

BLINKING_RED  = ["#255.0.0", "#0.0.0"]
GREEN         = ["#0.255.0", "#0.255.0"]
RED           = ["#255.0.0", "#255.0.0"]

def get_builderids(urlroot):
    '''Return a list of all the builder ids'''
    url = "%s/builders?field=builderid" % (urlroot)
    response=urllib.urlopen(url)
    response_json = json.loads(response.read())["builders"]
    builderids = [x["builderid"] for x in response_json]
    return builderids


def get_builders_without_active_workers(urlroot, builderids):
    '''Find any builders that don't have active workers.  These will never get built... and should be alarmed.'''
    url = "%s/workers?field=name&field=connected_to&field=configured_on&field=name&field=workerid"  % (urlroot)
    response=urllib.urlopen(url)
    response_json = json.loads(response.read())["workers"]
    workers = list()
    builders_with_no_workers = list(builderids)
    for worker in response_json:
        name = worker["name"]
        id = worker["workerid"]
        configured_on = worker["configured_on"]
        connected_to = worker["connected_to"]
        if len(configured_on) > 0:
            if len(connected_to) > 0 and len(configured_on) > 0:
                for configure in configured_on:
                    active_builder_id = int(configure["builderid"])
                    builders_with_no_workers.remove(active_builder_id)
        else:
            pass
    return builders_with_no_workers

def get_buildrequest(urlroot, buildrequestid):
    url = "%s/buildrequests?buildrequestid=%d" % (urlroot, buildrequestid)
    response = urllib.urlopen(url)
    buildrequest = json.loads(response.read())["buildrequests"][0]
    return buildrequest
    
def get_builder_status(urlroot, builderids):
    '''For each builder id:  Return the latest complete builds pass or fail status.  Also, return if that builder still has anything building.
    returns a list of ( (builderid, success?, building? ), ... )
    '''

    #
    # "builderid": 7,
    # "buildid": 893,
    # "buildrequestid": 1131,
    # "complete": false,
    # "complete_at": null,
    # "masterid": 1,
    # "number": 19,
    # "properties": {},
    # "results": null,
    # "started_at": 1516374598,
    # "state_string": "building",
    # "workerid": 9

    # Result Codes:
    #  SUCCESS  : 0
    #  WARNINGS : 1
    #  FAILURE  : 2
    #  SKIPPED  : 3
    #  EXCEPTION: 4
    #  RETRY    : 5
    #  CANCELLED: 6


    # status:  { builderid : [success?, building?], ... }
    status = {}
    for builderid in builderids:
        url = "%s/builds?builderid__eq=%d&order=-buildid&limit=2" % (urlroot, builderid)
        response = urllib.urlopen(url)
        builds = json.loads(response.read())["builds"]
        s = 0
        if len(builds) >= 1: # there have been at least 2 builds...:
            if builds[0]["complete"]:
                status[builderid] = [builds[0]["results"] == 0, False]
            else:
                # most recent build not complete.  How long is it not
                # complete for?  If taking more than, say 3 hours, better
                # notify  somebody...
                elapsed_time = (time.time() - builds[0]["started_at"])/3600
                if elapsed_time > 6:
                    status[builderid] = [False, False] # report an error
                    continue
                
                if len(builds) >=2:
                    if builds[1]["complete"]:
                        status[builderid] = [builds[1]["results"] == 0, True]
                    else:
                        # neither build is complete
                        status[builderid] = [False, True]
                else:
                    status[builderid] = [False, False]
        else:
            status[builderid] = [False, True]
    return status

def get_color_list(urlroot):
    builderids = get_builderids(urlroot)
    offline_builders = get_builders_without_active_workers(urlroot, builderids)
    builder_status = get_builder_status(urlroot, builderids)
    color_list = {}
    for builderid in builderids:
        if builderid in offline_builders:
            color = BLINKING_RED
        else:
            build_okay, building = builder_status[builderid]
            if build_okay:
                color = GREEN
            else:
                color = RED
        color_list[builderid] = color
    return builderids, color_list

def open_serial_port(port):
    """ Open the serial port.  Only return when a valid serial port has been opened."""
    ser = None
    while (ser == None):
        ser = serial.Serial(port, 9600, timeout=1)
        time.sleep(2)
    return ser

if __name__ == "__main__":
    check_interval = 10.0
    uart = "/dev/ttyUSB0"
    ser = open_serial_port(uart)
    ser.write("c\n")
    wakeup_time = time.time()
    blinker_phase = 0
    while(1):
        now = time.time()
        if  now > wakeup_time:
            wakeup_time = time.time() + check_interval
            try:
                builderids, color_list = get_color_list(urlroot)
            except IOError as e:
                print "Print got error: ", e
                continue
        else:
            time.sleep(0.5)
            blinker_phase = (blinker_phase+1)%2
            
        for builderid in builderids:
            color = color_list[builderid][blinker_phase]
            msg = "L%d%s\n" % (builderid, color)
            try:
                ser.write(msg)
            except:
                print "lost serial port, opening again."
                ser = open_serial_port(uart)
            
            
    
    
