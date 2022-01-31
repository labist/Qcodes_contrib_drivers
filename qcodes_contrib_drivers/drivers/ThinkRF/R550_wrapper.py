from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice
from pyrf.util import capture_spectrum
from pyrf.util import compute_usable_bins


import sys
import time
import math

from matplotlib.pyplot import plot, figure, axis, xlabel, ylabel, show
import numpy as np

from typing import Sequence, Union, Any


from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays, Enum

class GeneratedSetPoints(Parameter):
    """
    A parameter that generates a setpoint array from start, stop, and n_points

                           parameter_class=GeneratedSetPoints,
                           startparam=self.f_start,
                           stopparam=self.f_stop,
                           xpointsparam=self.n_points,
    """
    def __init__(self, startparam, stopparam, xpointsparam, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._startparam = startparam
        self._stopparam = stopparam
        self._xpointsparam = xpointsparam

    def get_raw(self):
        start = self._startparam()
        stop = self._stopparam()
        npts = self._xpointsparam()
        return np.linspace( start, stop, npts )

class SpectrumArray(ParameterWithSetpoints):
    
    def get_raw(self):
       
        dut = self.root_instrument.dut
        RBW = self.root_instrument._RBW
        average = self.root_instrument._average
        decimation = self.root_instrument.decimation

        fstart, fstop, spectra_data = capture_spectrum( dut,RBW,average,decimation)

        return spectra_data


class R550_wrapper(Instrument):
    ## wrapper around the pyRF API to use R550 with QCoDes
    def __init__(self,
                 name: str,
                 address: str,
                 **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        
        self.dut.reset()
        self.dut = WSA()
        self.dut.connect(address)
        self.dut.request_read_perm()


        self._freqstart = 5e9
        self._freqstop = 6e9
        self._span = 5e6

        self._RBW = 100e3
        self._average = 1
        self._decimation = 1
        self.rfe_mode('SH')
        
        self.add_parameter('rfe_mode',
                            unit = '',
                            label = 'Input Mode',
                            get_cmd = self.dut.rfe_mode,
                            set_cmd = self.dut.rfe_mode,
                            get_parser = str
                            )
        
        self.add_parameter('attenuation',
                                unit = 'dB',
                                label = 'attenuation',
                                get_cmd = self.dut.attenuator,
                                set_cmd = self.dut.attenuator,
                                get_parser = float,
                          )

        self.add_parameter('gain',
                                unit = '',
                                label = 'gain',
                                get_cmd = self.dut.psfm_gain,
                                set_cmd = self.dut.psfm_gain,
                                get_parser = str
                          )
        
        self.add_parameter('average',
                                unit = '',
                                label = 'average',
                                get_cmd = self.get_avg,
                                set_cmd = self.set_avg,
                                get_parser = float
                          )

        self.add_parameter('ppb',
                                unit = '',
                                label = 'packets/block',
                                get_cmd = self.dut.ppb,
                                set_cmd = self.dut.ppb,
                                get_parser = float,
                          )

        self.add_parameter('spp',
                                unit = '',
                                label = 'samples/packet',
                                get_cmd = self.dut.spp,
                                set_cmd = self.dut.spp,
                                get_parser = float,
                          )

        self.add_parameter('span',
                            unit = 'Hz',
                            label = 'span',
                           # vals = Numbers(0,100e6),
                            get_cmd = lambda : ,
                            set_cmd = self.set_bw ,
                            get_parser = float
                            )

        self.add_parameter('f_center',
                            unit = 'Hz',
                            label = 'f center',
                            vals = Numbers(0.1e9,27e9),
                            get_cmd = self.dut.freq,
                            set_cmd = self.dut.freq,
                            get_parser = float)

        self.add_parameter('f_start',
                            initial_value= 5.1e9,
                            unit='Hz',
                            label='f start',
                            #vals=Numbers(0,1e3),
                            get_cmd= self.get_fstart,
                            set_cmd=self.set_fstart,
                            get_parser = float)

        self.add_parameter('f_stop',
                            unit='Hz',
                            label='f stop',
                            #initial_value=fstop,
                            #vals=Numbers(1,1e3),
                            get_cmd = self.get_fstop,
                            set_cmd= self.get_fstop,
                            get_parser = float)

        self.add_parameter('n_points',
                            unit='',
                          # initial_value=len(spectra_data),
                            #vals=Numbers(1,1e3),
                            get_cmd= self.get_npoints,
                            set_cmd=self.set_npoints,
                            get_parser = float)
        
        self.add_parameter('freq_axis',
                            unit='Hz',
                            label='Freq',
                            parameter_class=GeneratedSetPoints,
                            startparam=self.f_start,
                            stopparam=self.f_stop,
                            xpointsparam=self.n_points,
                            vals=Arrays(shape=(self.n_points.get_latest,)))

        self.add_parameter('spectrum',
                            unit='dBm',
                            setpoints=(self.freq_axis,),
                            label='Noise power',
                            parameter_class=SpectrumArray,
                            dut = self.dut,
                            RBW = self._RBW,
                            average = self._average,
                            decimation = self.decimation,
                            vals=Arrays(shape=(self.n_points.get_latest,)))

    def set_bw(self,bw):
            '''
            function to set the bandwidth

                bw : bandwidth in Hz, float
            '''
            correctedBW = 1.25*bw ## correction so that the value set here is the usable bandwidth
            prevSpan = self.dut.properties.FULL_BW[self.rfe_mode()] 
            self.dut.properties.FULL_BW[self.rfe_mode()] = correctedBW
            self.dut.properties.USABLE_BW[self.rfe_mode()]= bw

            spanChangeFactor = correctedBW/prevSpan 
            self._RBW = self._RBW * spanChangeFactor ## correction to resolution so that number of points stays the same
    
    def set_npoints(self,n):
            self._RBW = 0.81 * self.span()/n ## approximate correction to compensate for usable bins calculation

    def get_npoints(self):
            fstart, fstop, spectra_data = capture_spectrum(self.dut,self._RBW)
            return len(spectra_data)

    def get_fstart(self):
            return self._fstart

    def set_fstart(self, f):
            self._fstart = f

    def get_fstop(self):
            return self._fstop

    def set_fstop(self, f):
            self._fstop = f

    def get_avg(self):
            return self._average

    def set_avg(self, avg):
            self._average = avg

    def get_span(self):
            return self._span

    def set_span(self, bw):
            self._span = bw