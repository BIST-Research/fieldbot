#
# Author: Ben Westcott
# Date created: 10/28/23
#

from queue import Empty, Queue
from threading import Event, Thread
from time import sleep

import os

import gpxpy
import gpxpy.gpx


from pynmeagps import NMEAMessageError, NMEAParseError
from pyrtcm import RTCMMessage, RTCMMessageError, RTCMParseError
from serial import Serial

from datetime import datetime
from time import strftime

#from bb_utils import search_comports

from pyubx2 import(
    NMEA_PROTOCOL,
    RTCM3_PROTOCOL,
    UBX_PROTOCOL,
    UBXMessage,
    UBXMessageError,
    UBXParseError,
    UBXReader,
    VALCKSUM
)

XML_HDR = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

GPX_NS = " ".join(
    (
        'xmlns:"http://www.topografix.com/GPX/1/1"',
        'creator="bepiis" version="1.0"',
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        'xsi:schemaLocation="http://www.topografix.com/GPX/1/1"',
        '"http://www.topografix.com/GPX/1/1/gpx.xsd"'
    )
)

GITHUB_LINK = "https://github.com/BIST-Research/"

class mlgps:

    def __init__(
        self,
        port: str,
        baudrate: int,
        timeout: float,
        stopevent: Event,
        sendqueue: Queue,
        ubxenable: bool,
        dump_path: str,
        bat_log
    ):
        
        self.port = port
        self.bat_log = bat_log
        
        #if str(self.port) == "None":
        #    self.bat_log.critical(f"Could not find GPS device with listed serial numbers!")
        #    raise IOError

        self.baud_rate = baudrate        
        self.timeout = timeout
        self.stopevent = stopevent
        self.stream = None
        self.connected = False
        self.ubxenable = ubxenable
        self.sendqueue = sendqueue
        self.dump_path = dump_path
        
        self._trkfname = None
        self._trkfile = None
        
        self.lat = 0
        self.lon = 0
        self.alt = 0
        self.sep = 0
        
        self.gpx = gpxpy.gpx.GPX()
        self.gpx_track = gpxpy.gpx.GPXTrack()
        self.gpx.tracks.append(self.gpx_track)
        self.gpx_segment = gpxpy.gpx.GPXTrackSegment()
        self.gpx_track.segments.append(self.gpx_segment)

        
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.stop()
        
    def run(self):
        
        self.ubx_enable(self.ubxenable)
        
        self.stream = Serial(self.port, self.baud_rate, timeout=self.timeout)
        self.connected = True
        self.stopevent.clear()
        
        reader_thread = Thread(
            target=self._read_loop, 
            args=(
                self.stream,
                self.stopevent,
                self.sendqueue
            ),
            daemon=True
        )
        
        reader_thread.start()
        
    def stop(self):

        self.stopevent.set()
        self.connected = False
        if self.stream is not None:
            #self.bat_log.info(f"Closing connection with {self.port}")
            self.stream.close()

        
    def _read_loop(self, stream: Serial, stopevent: Event, sendqueue: Queue):
        
        ubx_reader = UBXReader(
            stream,
            protfilter = (NMEA_PROTOCOL | UBX_PROTOCOL | RTCM3_PROTOCOL),
            validate = VALCKSUM
        )
        
        while not stopevent.is_set():
            try:
                if stream.in_waiting:
                    _, msg = ubx_reader.read()
                    
                    if msg:
                        self._extract_coordinates(msg)
                        #print(f"{self.lon}")
                        
                        if msg.identity == "NAV-PVT":

                            time = datetime(msg.year, msg.month, msg.day, msg.hour, msg.min, msg.second)

                            if msg.fixType == 3:
                                fix = "3d"
                            elif msg.fixType == 2:
                                fix = "2d"
                            else:
                                fix = "none"
                            
                            tkpoint = gpxpy.gpx.GPXTrackPoint(
                                msg.lat, msg.lon, elevation=msg.hMSL/100, time=time
                            )
                            #print(msg)
                            tkpoint.type_of_gpx_fix=fix
                            self.gpx_segment.points.append(tkpoint)

                        
                if self.sendqueue is not None:
                    self._send_data(ubx_reader.datastream, sendqueue)
                    
                        
            except(UBXMessageError, UBXParseError, NMEAMessageError, NMEAParseError, RTCMMessageError, RTCMParseError) as err:
                #self.bat_log.warning(f"Exception thrown while parsing stream: {err}")
                continue
                
        self.write_gpx_tlr()

            
            
    def _extract_coordinates(self, msg: object):
        if hasattr(msg, "lat"):
    	    self.lat = msg.lat
        if hasattr(msg, "lon"):
    	    self.lon = msg.lon
        if hasattr(msg, "alt"):
    	    self.alt = msg.alt    	    
        if hasattr(msg, "hMSL"):
    	    self.alt = msg.hMSL/1000
        if hasattr(msg, "sep"):
    	    self.sep = msg.sep
        if hasattr(msg, "hMSL") and hasattr(msg, "height"):
    	    self.sep = (msg.height - msg.hMSL)/1000

    def get_coordinates(self) -> tuple:
        return (self.connected, self.lat, self.lon, self.alt, self.sep)

    def _send_data(self, stream: Serial, sendqueue: Queue):
        
        if sendqueue is not None:
            try:
                while not sendqueue.empty():
                    data = sendqueue.get(False)
                    raw, parsed = data
                    
                    # source = "NTRIP>>" if isinstance(parsed, RTCMMEssage) else "GNSS<<"

                    stream.write(raw)
                    sendqueue.task_done()
                    
            except Empty:
                pass
            
    def ubx_enable(self, enable: bool):
        
        layers = 1
        transaction = 0
        cfg_data = []
        
        for port_type in ("USB", "UART1"):
            cfg_data.append((f"CFG_{port_type}OUTPROT_NMEA", not enable))
            cfg_data.append((f"CFG_{port_type}OUTPROT_UBX", enable))
            cfg_data.append((f"CFG_MSGOUT_UBX_NAV_PVT_{port_type}", enable))
            cfg_data.append((f"CFG_MSGOUT_UBX_NAV_SAT_{port_type}", enable * 4))
            cfg_data.append((f"CFG_MSGOUT_UBX_NAV_DOP_{port_type}", enable * 4))
            cfg_data.append((f"CFG_MSGOUT_UBX_RXM_RTCM_{port_type}", enable))
        
        msg = UBXMessage.config_set(layers, transaction, cfg_data)
        self.sendqueue.put((msg.serialize(), msg))
        
    def write_gpx_header(self):
        
        timestamp = strftime("%Y%m%d%H%M%S")
        self._trkfname = os.path.join(self.dump_path, f"gpxtrack-{timestamp}.gpx")
        self._trkfile = open(self._trkfname, "a")
        
        date = datetime.now().isoformat()
        
        gpxtrack = (
            XML_HDR + "<gpx>"
            "<metadata>"
            f'<link href="{GITHUB_LINK}"><text>bepiis</text></link><time>{date}</time>'
            "</metadata>"
            "<trk><name>GPX track from UBX NAV-PVT datalog</name><trkseg>"
        )
        
        self._trkfile.write(gpxtrack)
        
    def write_gpx_trkpnt(self, lat, lon, ele, time, fix):
        
        trkpnt = f'<trkpnt> lat="{lat}" lon="{lon}"'
        trkpnt += f"<ele>{ele}</ele>"
        trkpnt += f"<time>{time}</time>"
        trkpnt += f"<fix>{fix}</fix>"
        trkpnt += f"</trkpnt>"
        
        self._trkfile.write(trkpnt)
                        
    def write_gpx_tlr(self):
        #gpxtrack = "</trkseg></trk></gpx>"
        #self._trkfile.write(gpxtrack)
        #self._trkfile.close()
        
        timestamp = strftime("%Y%m%d%H%M%S")
        gpx_name = os.path.join(self.dump_path, f"gpx_{timestamp}.gpx")
        xml_out = self.gpx.to_xml()
        print(xml_out)
        with open(gpx_name, "w") as gpx_write:
            gpx_write.write(xml_out)
            gpx_write.close()
        	
                
                
                            
if __name__ == "__main__":
    outdir = "/home/jetson/fieldbot"
    ser_port = "/dev/ttyACM1"
    #bat_log = bb_log.get_log()
    
    send_queue = Queue()
    stop_event = Event()
    try:
        with mlgps(ser_port, 9600, 3, stop_event, send_queue, True, outdir, "B") as gna:
            gna.run()
            while True:
                sleep(1)
            
    except KeyboardInterrupt:
        stop_event.set()
        
        
        
        
        
    
