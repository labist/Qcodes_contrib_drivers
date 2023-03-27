#%%
import numpy as np
from qcodes import Instrument, ParameterWithSetpoints
from qcodes.utils.validators import Arrays
from pyrf.devices.thinkrf import WSA
from pyrf.sweep_device import SweepDevice
from pyrf.numpy_util import calculate_channel_power

# TODO: make these into parameters
# TODO: add a channel_power command
# TODO: add attenuator
RBW = 400e3
# RFE_MODE = 'SH'
# START_FREQ = 1.39e9
# STOP_FREQ = 1.41e9

class R5550(Instrument):
    """ R5550 insturment class. Wraps the capture_power_spectrum method provided by thinkrf
    """
    def __init__(self, name, address, start=1e6, stop=10e9, navg=1, rfe='SH', rbw=400e3, attenuator=0 ):
        """
        Create R5550
        Args:
            name: qcodes paramter name
            address: ip address
            start: start frequency in Hz
            stop: stop frequency in Hz
            navg: number of averages
            rfe: one of SH, SHN, ..
            rbw: resolution bandwidth in Hz
            attenuator: attenuator setting in dB
        """

        super().__init__(name=name)
        self.address = address
        dut = WSA()
        dut.connect(self.address)
        dut.request_read_perm()
        dut.configure_flattening(loaded=None)
        self.sd = SweepDevice(dut)

        self._navg = navg
        self.add_parameter('averages', 
                           label='Averages', 
                           unit='#', 
                           get_cmd = lambda : getattr(self, '_navg'),
                           set_cmd = lambda  n : setattr(self, '_navg', n))

        self._rbw=rbw               
        self.add_parameter('rbw', 
                           label='RBW', 
                           unit='Hz', 
                           get_cmd = lambda : getattr(self, '_rbw'),
                           set_cmd = lambda  n : setattr(self, '_rbw', n))

        self._start=start
        self.add_parameter('start', 
                           label='starting frequency', 
                           unit='Hz', 
                           get_cmd = lambda : getattr(self, '_start'),
                           set_cmd = lambda  n : setattr(self, '_start', n))

        self._stop=stop
        self.add_parameter('stop', 
                           label='stopping frequency', 
                           unit='Hz', 
                           get_cmd = lambda : getattr(self, '_stop'),
                           set_cmd = lambda  n : setattr(self, '_stop', n))

        self._rfe=rfe
        self.add_parameter('rfe', 
                           label='RFE Mode', 
                           unit='mode', 
                           get_cmd = lambda : getattr(self, '_rfe'),
                           set_cmd = lambda  n : setattr(self, '_rfe', n))
        
        self._attenuator=attenuator
        self.add_parameter('attenuator', 
                           label='Attenuator', 
                           unit='dB', 
                           get_cmd = lambda : getattr(self, '_attenuator'),
                           set_cmd = lambda  n : setattr(self, '_attenuator', n))
        
        self.add_parameter('channel_power', 
                           label='Channel Power', 
                           unit='dBm', 
                           get_cmd = self.get_channel_pwr)

        self._freq = self.refresh_faxis()

        self.add_parameter('freq_axis',
                           unit='Hz',
                           label='$f$',
                           get_cmd=lambda : self._freq,
                           vals=Arrays(shape=(self._freq.size,)))
        

        self.add_parameter('spectrum',
                   unit='dBm',
                   setpoints=(self.freq_axis,),
                   label='Noise power',
                   parameter_class=ParameterWithSetpoints,
                   get_cmd=self._get_spectrum,
                   vals=Arrays(shape=(self._freq.size,)))

    def capture(self) :
        """ run a capture
        Returns:
            fstart, fstop, spectrum
        """
        sd = self.sd
        device_settings = dict(rfe_mode=self.rfe(), attenuator=self.attenuator())
        cap = sd.capture_power_spectrum(self.start(), self.stop(),
            self.rbw(), device_settings=device_settings,
            mode = self.rfe(), continuous=False)
        return cap
    
    def connect(self) :
        """ connect to WSA
        """
        dut = WSA()
        dut.connect(self.ip)
        dut.request_read_perm()
        dut.configure_flattening(loaded=None)
        self.sd = SweepDevice(dut)

    def refresh_faxis(self) :
        """ refresh internal frequency axis. should be called after changing start/stop range
        """
        fstart, fstop, spectral_data = self.capture()
        return np.linspace(fstart,fstop,len(spectral_data))
    
    def _get_spectrum(self):
        """ get an averaged spectrum
        """
        navg = self.averages()

        spectra_sum = np.zeros(self._freq.size)
        for _ in range(navg) :
            _, _, spectrum = self.capture()
            spectra_sum += spectrum
        return spectra_sum / navg
    
    def get_channel_pwr(self):
        """ calculate channel power from averaged spectrum
        """
        return calculate_channel_power(self._get_spectrum())

# spec = R5550(name='r5550', ip='169.254.16.253')
