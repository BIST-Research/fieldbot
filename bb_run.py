#
# Date created: 4/3/23
# Author: Ben Westcott
#

import numpy as np
import serial
import serial.tools.list_ports
import time
import math
import os
import sys
import logging
import yaml
from subprocess import Popen, PIPE
import signal as sig
from bb_plot import BBPlotter

from scipy import signal
from batbot import BatBot
from batbot import bin2dec
from bb_gps import get_gps_exec_line

import bb_log

from datetime import datetime
from m4 import M4

bat_log = bb_log.get_log()
    
if __name__ == '__main__':
    
    nruns = 0
    
    if len(sys.argv) < 2:
        nruns = -1
    else:
        nruns = int(sys.argv[1])
        
    bb = BatBot(bat_log)
    
    bb.run()
    bb.run()
    
    gps_book = bb.get_gps_book()
    run_dir = bb.get_run_directory()
    process = None
    
    do_gps = bool(gps_book['do_gps'])
    do_plot = bb.get_do_plot()
    
    if do_gps:
    	exec_line = get_gps_exec_line(gps_book, run_dir)
    	bat_log.info(f"Starting GPS interface...")
    	process = Popen(exec_line, stdin=PIPE, stdout=PIPE, stderr=PIPE)
	
    # first calibration run
    initial_calib_data = bb.run()
    
    plotter = None
    if do_plot:
        plotter = BBPlotter(bat_log, bb.echo_book, initial_calib_data)
    
    nruns_idx = 0
    time_start = datetime.now()
    
    echo0_total, echo1_total = [],[]
    progress_interval = 50
    

    bb.send_sweep_freqs()

    bb.send_amp_start()
    
    while True:

        try:
            if nruns_idx == nruns:
                break
            
            echo_data = bb.run()
            if do_plot:
                echo1_total = np.append(echo1_total, echo_data[1])
                echo0_total = np.append(echo0_total, echo_data[0])
                
                if nruns_idx % plotter.echo_calibration_interval == 0:
                    plotter.echo_calibration_run(echo_data)

                if nruns_idx % plotter.echo_plot_interval == 0:
                    time_elapsed = datetime.now() - time_start
                    
                    plotter.update_super_title(time_elapsed, nruns_idx)
                    plotter.update_plots([echo0_total, echo1_total])
                    
                    echo0_total, echo1_total = [],[]
     
            
            if nruns_idx % progress_interval == 0:
                if nruns == -1:
                    bat_log.info(f"{nruns_idx}")
                else:
                    bat_log.info(f"{nruns_idx}/{nruns}")
            #    gps_stdout = process.stdout.readline()
            #    if gps_stdout:
            #        print(gps_stdout)

            nruns_idx += 1   
        

        except KeyboardInterrupt:
            print("")
            bat_log.info("Interrupted")
            break

    if do_gps:
        os.kill(process.pid, sig.SIGINT)
        
    bb.send_amp_stop()
    time_finish = datetime.now() - time_start
    bat_log.info(f"{nruns} runs took {time_finish}")
