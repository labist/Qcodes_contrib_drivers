#%%
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice
from pyrf.util import capture_spectrum
from pyrf.util import compute_usable_bins


import sys
import time
import math

from matplotlib.pyplot import plot, figure, axis, xlabel, ylabel, show
import numpy as np

from qcodes.instrument.base import Instrument
from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter
from qcodes.dataset.measurements import Measurement
from qcodes.utils.validators import Numbers, Arrays, Enum


## Testing the capture with averages
#%%
# declare sweep constants
START_FREQ = 50e6
STOP_FREQ = 19e9
RBW = 100e3

#%%
# connect to wsa
dut = WSA()
dut.connect('169.254.16.253')
dut.request_read_perm()
# declare sweep device
#sd = SweepDevice(dut)

#%%
# read the spectral data
#fstart, fstop, spectra_data = sd.capture_power_spectrum(START_FREQ, STOP_FREQ, RBW,
 #     {'attenuator':0})

fstart, fstop, spectra_data = capture_spectrum(dut,RBW,average=10)
#%%
# setup my graph
fig = figure(1)
xvalues = np.linspace(fstart, fstop, len(spectra_data))

xlabel("Frequency")
ylabel("Amplitude")

# plot something
plot(xvalues, spectra_data, color='blue')

# show graph
show()
# %%
# %%
## Array Parameter Qcodes
class GeneratedSetPoints(Parameter):
    """
    A parameter that generates a setpoint array from start, increment, and n_points

                               parameter_class=GeneratedSetPoints,
                           startparam=self.x_start,
                           incparam=self.x_inc,
                           xpointsparam=self.x_points,
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
        RBW = self.root_instrument.RBW
        average = self.root_instrument.average
        decimation = self.root_instrument.decimation

        fstart, fstop, spectra_data = capture_spectrum( dut,RBW,average,decimation)

        return spectra_data


class DummyInstrument(Instrument):

    def __init__(self, name, RBW=100e3, average=1, decimation = 1, **kwargs):
        super().__init__(name, **kwargs)

        self.dut = WSA()
        self.dut.connect('169.254.16.253')
        self.dut.request_read_perm()
        self.RBW = RBW
        self.average = average
        self.decimation = decimation

        
        self.add_parameter('f_center',
                            unit = 'Hz',
                            label = 'f center',
                            vals = Numbers(0.1e9,27e9),
                            get_cmd = self.dut.freq,
                            set_cmd = self.dut.freq,
                            get_parser = float)

        self.add_parameter('rfe_mode',
                            unit = '',
                            label = 'Input Mode',
                            get_cmd = self.dut.rfe_mode,
                            set_cmd = self.dut.rfe_mode,
                            get_parser = str
                            )

        self.add_parameter('span',
                            unit = 'Hz',
                            label = 'span',
                            vals = Numbers(0,100e6),
                            get_cmd = lambda : self.dut.properties.FULL_BW[self.rfe_mode()],
                            set_cmd = self.set_bw ,
                            get_parser = float
                            )

        self.add_parameter('f_start',
                            #initial_value=fstart,
                            unit='Hz',
                            label='f start',
                            #vals=Numbers(0,1e3),
                            get_cmd= self.get_fstart,
                            set_cmd=None,
                            get_parser = float)

        self.add_parameter('f_stop',
                            unit='Hz',
                            label='f stop',
                            #initial_value=fstop,
                            #vals=Numbers(1,1e3),
                            get_cmd = self.get_fstop,
                            set_cmd=None,
                            get_parser = float)

        self.add_parameter('n_points',
                            unit='',
                          #  initial_value=len(spectra_data),
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
                            RBW = self.RBW,
                            average = self.average,
                            decimation = self.decimation,
                            vals=Arrays(shape=(self.n_points.get_latest,)))

    def set_bw(self,bw):

            correctedBW = 1.25*bw
            prevSpan = self.dut.properties.FULL_BW[self.rfe_mode()] 
            self.dut.properties.FULL_BW[self.rfe_mode()] = correctedBW
            self.dut.properties.USABLE_BW[self.rfe_mode()]= bw

            spanChangeFactor = correctedBW/prevSpan
            self.RBW = self.RBW * spanChangeFactor
    
    def set_npoints(self,n):
            self.RBW = 0.81 * self.span()/n

    def get_npoints(self):
            fstart, fstop, spectra_data = capture_spectrum(self.dut,self.RBW)
            print(len(spectra_data))
            return len(spectra_data)

    def get_fstart(self):
            fstart, fstop, spectra_data = capture_spectrum(self.dut,self.RBW)
            return fstart

    def get_fstop(self):
            fstart, fstop, spectra_data = capture_spectrum(self.dut,self.RBW)
            return fstop
# %%
dummyInst = DummyInstrument('demo4')
#%%
dummyInst.span(50e6)
# %%
dummyInst.n_points()
s = dummyInst.spectrum()

# %%
# %%
f = dummyInst.spectrum.setpoints[0]()
# %%
from hlab.data_io.qc_sweeps import do0d, do1d
import hlab, hlab.setup.new

hsetup = hlab.setup.new.experiment( sample='load2', 
            path_to_station = 'mw_2deg/jpa/station.yml',
            path_to_db='mw_2deg/jpa/p17.db' )
# %%
do0d(dummyInst.spectrum)
# %%
