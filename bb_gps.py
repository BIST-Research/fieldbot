#
# Author: Ben Westcott
# Date created: 10/28/23
#

from queue import Queue, Empty
from threading import Event
from time import sleep

from pygnssutils import VERBOSITY_LOW, VERBOSITY_MEDIUM, GNSSNTRIPClient
from mlgps import mlgps
#from gnssapp import GNSSSkeletonApp

import sys
import bb_log
import yaml

CONNECTED = 1

def get_gps_exec_line(gps_book, run_dir):
    ntrip_book = gps_book['ntrip']
    exec_line = [
        "py3",
        "bb_gps.py",
        f"{gps_book['ser_port']}",
        f"{gps_book['baud_rate']}",
        f"{gps_book['timeout']}",
        f"{ntrip_book['ipprot']}",
        f"{ntrip_book['server']}",
        f"{ntrip_book['port']}",
        f"{ntrip_book['username']}",
        f"{ntrip_book['password']}",
        f"{ntrip_book['ggamode']}",
        f"{ntrip_book['ggaint']}",
        f"{ntrip_book['reflat']}",
        f"{ntrip_book['reflon']}",
        f"{ntrip_book['refalt']}",
        f"{ntrip_book['refsep']}",
        f"{run_dir}"
    ]
    return exec_line

if __name__ == "__main__":
    
    batlog = bb_log.get_log()
        
    ser_port = str(sys.argv[1])
    baud_rate = str(sys.argv[2])
    timeout = int(sys.argv[3])
    #do_rtk = bool(sys.argv[4])
    ntrip_ipprot = str(sys.argv[4])
    ntrip_server = str(sys.argv[5])
    ntrip_port = int(sys.argv[6])
    ntrip_mountpoint = ""
    ntrip_username = str(sys.argv[7])
    ntrip_password = str(sys.argv[8])
    ntrip_ggamode = int(sys.argv[9])
    ntrip_ggint = int(sys.argv[10])
    ntrip_reflat = float(sys.argv[11])
    ntrip_reflon = float(sys.argv[12])
    ntrip_refalt = float(sys.argv[13])
    ntrip_refsep = float(sys.argv[14])
    run_dir = str(sys.argv[15])

    send_queue = Queue()
    sourcetable_queue = Queue()
    stop_event = Event()
    
    try:
        stdout_fd = open(f"{run_dir}/gps_stdout.log", "w")
        stdout_fd.write(f"Starting GNSS reader/writer on {ser_port} @ {baud_rate}...\n")


        with mlgps(
           ser_port,
           baud_rate,
           timeout,
           dump_path=run_dir,
           stopevent=stop_event,
           sendqueue=send_queue,
           ubxenable=True,
           bat_log = batlog
           
        ) as gna:
            gna.run()
            sleep(2)
            
            mountpoint = ""
            stdout_fd.write(f"Retrieving closest mountpoint from {ntrip_server}:{ntrip_port}...\n")

            with GNSSNTRIPClient(gna, verbosity=VERBOSITY_LOW) as gnc:
                streaming = gnc.run(
                    ipprot=ntrip_ipprot,
                    server=ntrip_server,
                    port=ntrip_port,
                    mountpoint=ntrip_mountpoint,
                    ntripuser=ntrip_username,
                    ntrippassword=ntrip_password,
                    reflat=ntrip_reflat,
                    reflon=ntrip_reflon,
                    refalt=ntrip_refalt,
                    refsep=ntrip_refsep,
                    ggamode=ntrip_ggamode,
                    ggainterval=ntrip_ggint,
                    output=sourcetable_queue
                )
                
                try:
                    srt, (mountpoint, dist) = sourcetable_queue.get(timeout=3)
                    #print(f"{srt}\n\n")
                    if mountpoint is None:
                        raise Empty
                        
                    stdout_fd.write(f"Closest mountpoint is {mountpoint} which is {dist} km away\n")

                except Empty:
                    stop_event.set()
                    stdout_fd.write("Unable to find closest mountpoint -- quitting...\n")

            
            ntrip_address = f"{ntrip_server}:{ntrip_port}/{mountpoint}"
            stdout_fd.write(f"Streaming RTCM3 data from {ntrip_address}...\n")

            with GNSSNTRIPClient(gna, verbosity=VERBOSITY_MEDIUM, logtofile=1, logpath=run_dir) as gnc:
                streaming = gnc.run(
                    server=ntrip_server,
                    port=ntrip_port,
                    mountpoint=mountpoint,
                    ntripuser=ntrip_username,
                    ntrippassword=ntrip_password,
                    output=send_queue
                )


                while(
                    streaming and not stop_event.is_set()
                ):
                    sleep(1)
                sleep(1)
                stdout_fd.close()
                
    except KeyboardInterrupt:
        stop_event.set()
        #stdout_fd.write("Terminated by user")
       

