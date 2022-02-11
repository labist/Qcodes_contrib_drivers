import numpy as np
from typing import Sequence, Union, Any

# from qcodes.instrument.base import Instrument
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays, Enum

from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter
from qcodes import VisaInstrument

import socket
class GeneratedSetPoints(Parameter):
    """
    A parameter that generates a setpoint array from start, increment, and n_points

                               parameter_class=GeneratedSetPoints,
                           startparam=self.x_start,
                           incparam=self.x_inc,
                           xpointsparam=self.x_points,
    """
    def __init__(self, startparam, incparam, xpointsparam, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._startparam = startparam
        self._incparam = incparam
        self._xpointsparam = xpointsparam

    def get_raw(self):
        start = self._startparam()
        inc = self._incparam()
        npts = self._xpointsparam()
        stop = start + inc * ( npts - 1 )
        return np.linspace( start, stop, npts )

class SpectrumArray(ParameterWithSetpoints):

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)            

    def get_raw(self):
        # :TRACe[:DATA]? need to test this live
        # i think we can access the visa resource with somethign like self.instrument.visa_handle
        sa = self.instrument
        visa_handle = sa.visa_handle

        visa_handle.query("SYSTEM:LOCK:REQUEST? ACQ")
        visa_handle.write(":TRACe:SPP %s" % (256))
        visa_handle.write(":TRACe:BLOCK:PACKETS %s" % (1))
        
        print( visa_handle.query(":SYSTem:ERRor:CODE:ALL?") )

        # Trigger a sweep, and wait for it to complete
        visa_handle.query('*OPC?' )
        visa_handle.write( ':TRACe:BLOCK:DATA?' )
        
        self.root_instrument.vrt_socket_connect()
        data_str = yield self.root_instrument.vrt_read(2)
        print("past the yield")
        print(type(data_str))
        R550_visa.vrt_socket_disconnect()

        return np.fromstring( data_str, sep=',' )

class R550_visa(VisaInstrument):
    ## module to interact directly with R550 using VISA, not fully functional
    def __init__(self,
                 name: str,
                 address: str,
                 **kwargs: Any) -> None:
        super().__init__(name, address, terminator='\n', **kwargs)
        self.vrt_socket = None
        #         # Number of averages (also resets averages)
        # self.add_parameter('averages_enabled',
        #                    label='Averages Enabled',
        #                    get_cmd="SENS:AVER?",
        #                    set_cmd="SENS:AVER {}",
        #                    val_mapping={True: '1', False: '0'})



        # self.add_parameter('f_start',
        #                 unit='Hz',
        #                 label='f start',
        #                 vals=Numbers(0,30e9),
        #                 get_cmd=  ":TRIG:LEVEL?",
        #            #     set_cmd= ":TRIG:LEVEL {}" + " " + self.get_trigger(param='f_stop') + " " + self.get_trigger(param='trig_level'),
        #                 get_parser=float )
    
        # self.add_parameter('f_stop',
        #                 unit='Hz',
        #                 label='f stop',
        #                 vals=Numbers(0,30e9),
        #                 get_cmd=self.get_trigger(param='f_stop'),
        #                 set_cmd= f"TRIG:LEVEL {self.get_trigger(param='f_start')} " + "{}" + f" {self.get_trigger(param='trig_level')}",
        #                 get_parser=float )

        self.add_parameter('f_center',
                        unit='Hz',
                        label='f center',
                        vals=Numbers(0,30e9),
                        get_cmd=":SENSe:FREQuency:CENTER?",
                        set_cmd=":SENSe:FREQuency:CENTER {}",
                        get_parser=float )

        self.add_parameter('f_shift',
                        unit='Hz',
                        label='f center',
                        vals=Numbers(0,30e9),
                        get_cmd=":SENSe::FREQuency:SHIFt?",
                        set_cmd=":SENSe::FREQuency:SHIFt {}",
                        get_parser=float )
    
        # self.add_parameter('trig_level',
        #                 unit='dBm',
        #                 label='Trigger Level',
        #                 vals=Numbers(-100,100),
        #                 get_cmd=self.get_trigger(param='trig_level'),
        #                 set_cmd= f"TRIG:LEVEL {self.get_trigger(param='f_start')} {self.get_trigger(param='f_stop')} "+"{}",
        #                 get_parser=float )

        # self.add_parameter('freq_axis',
        #                    unit='Hz',
        #                    label='Freq',
        #                    parameter_class=GeneratedSetPoints,
        #                    startparam=500e6,
        #                    incparam=26000e6/(32*32),
        #                    xpointsparam=26500e6,
        #                    vals=Arrays(shape=(32*32*1,)))

        self.add_parameter('spectrum',
                    unit='dBm',
             #       setpoints=(self.freq_axis,),
                    label='Noise power',
                    parameter_class=SpectrumArray,
                    vals=Arrays(shape=(32*32*1,))) # SPP * npackets

    def get_trigger(self,arg=None):
        
        triglevel = self.scpi_read("TRIG:LEVEL?").split(',')

        if (arg=='f_start'):
            return triglevel[0]
        
        elif (arg=='f_stop'):
            return triglevel[1]
        
        elif (arg=='trig_level'):
            return triglevel[2]
        
        else:
            return "Invalid argument"


    def scpi_write(self, cmd):

        self.write(cmd)

    def scpi_read(self, cmd):
        """
        Send a SCPI *query* command and wait for the response.
        This is the lowest-level interface provided.  See the product's
        Programmer's Guide for the SCPI commands available.
        :param str cmd: the SCPI command to send
        :return: the response output from the box if any
        """
        return self.ask(cmd)
    
    def system_flush(self):

        self.write(":SYSTEM:FLUSH")
    
    def vrt_socket_connect(self, vrt_port=37000, timeout=10):
        self.vrt_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.vrt_socket.connect((self._address[8:22], vrt_port))
    
    def vrt_socket_disconnect(self):
         self.vrt_socket.shutdown(socket.SHUT_RDWR)
       
    
    def vrt_read(self, count, flags = None):
        """
        Retry socket read until *count* amount of data received,
        like reading from a file.
        :param int count: the amount of data received
        :param flags: socket.recv() related flags
        """

        data = self.vrt_socket.recv(count)
        datalen = len(data)
        print(datalen)
        if datalen == 0:
            return False

        while datalen < count:
            data = data + socket.recv(count - datalen)
            datalen = len(data)

        print("vrt_read output")
        print(data)
        return data