from typing import Dict, List, Optional, Sequence, Any, Union
from functools import partial
import numpy as np
import logging
log = logging.getLogger(__name__)

import time
import matplotlib.pyplot as plt
import numpy as np

import zhinst.utils
import qcodes as qc
from qcodes.instrument.base import Instrument
import qcodes.utils.validators as vals

from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter

from qcodes.dataset.measurements import Measurement, res_type, DataSaver
from qcodes.instrument.specialized_parameters import ElapsedTimeParameter

class HF2LI(Instrument):
    """Qcodes driver for Zurich Instruments HF2LI lockin amplifier.

    This driver is meant to emulate a single-channel lockin amplifier,
    so one instance has a single demodulator, a single sigout channel,
    and multiple auxout channels (for X, Y, R, Theta, or an arbitrary manual value).
    Multiple instances can be run simultaneously as independent lockin amplifiers.

    This instrument has a great deal of additional functionality that is
    not currently supported by this driver.

    Args:
        name: Name of instrument.
        device: Device name, e.g. "dev204", used to create zhinst API session.
        demod: Index of the demodulator to use.
        sigout: Index of the sigout channel to use as excitation source.
        auxouts: Dict of the form {output: index},
            where output is a key of HF2LI.OUTPUT_MAPPING, for example {"X": 0, "Y": 3}
            to use the instrument as a lockin amplifier in X-Y mode with auxout channels 0 and 3.
        num_sigout_mixer_channels: Number of mixer channels to enable on the sigouts. Default: 1.
    """
    OUTPUT_MAPPING = {-1: 'manual', 0: 'X', 1: 'Y', 2: 'R', 3: 'Theta'}
    def __init__(self, name: str, device: str, demod: int, sigout: int,
        auxouts: Dict[str, int], num_sigout_mixer_channels: int=1, **kwargs) -> None:
        super().__init__(name, **kwargs)
        instr = zhinst.utils.create_api_session(device, 1, required_devtype='HF2LI') #initializes the instrument
        self.daq, self.dev_id, self.props = instr
        self.demod = demod
        self.sigout = sigout
        self.auxouts = auxouts
        log.info(f'Successfully connected to {name}.')
        
        for ch in self.auxouts:
            self.add_parameter(
                name=ch,
                label=f'Scaled {ch} output value',
                unit='V',
                get_cmd=lambda channel=ch: self._get_output_value(channel),
                get_parser=float,
                docstring=f'Scaled and demodulated {ch} value.'
            )
            self.add_parameter(
                name=f'gain_{ch}',
                label=f'{ch} output gain',
                unit='V/Vrms',
                get_cmd=lambda channel=ch: self._get_gain(channel),
                get_parser=float,
                set_cmd=lambda gain, channel=ch: self._set_gain(gain, channel),
                vals=vals.Numbers(),
                docstring=f'Gain factor for {ch}.'
            )
            self.add_parameter(
                name=f'offset_{ch}',
                label=f'{ch} output offset',
                unit='V',
                get_cmd=lambda channel=ch: self._get_offset(channel),
                get_parser=float,
                set_cmd=lambda offset, channel=ch: self._set_offset(offset, channel),
                vals=vals.Numbers(-2560, 2560),
                docstring=f'Manual offset for {ch}, applied after scaling.'
            )
            self.add_parameter(
                name=f'output_{ch}',
                label=f'{ch} outptut select',
                get_cmd=lambda channel=ch: self._get_output_select(channel),
                get_parser=str
            )
            # Making output select only gettable, since we are
            # explicitly mapping auxouts to X, Y, R, Theta, etc.
            self._set_output_select(ch)
            
        self.add_parameter(
            name='phase',
            label='Phase',
            unit='deg',
            get_cmd=self._get_phase,
            get_parser=float,
            set_cmd=self._set_phase,
            vals=vals.Numbers(-180,180)
        )
        self.add_parameter(
            name='time_constant',
            label='Time constant',
            unit='s',
            get_cmd=self._get_time_constant,
            get_parser=float,
            set_cmd=self._set_time_constant,
            vals=vals.Numbers()
        )  
        self.add_parameter(
            name='frequency',
            label='Frequency',
            unit='Hz',
            get_cmd=self._get_frequency,
            set_cmd=self._set_frequency,
            get_parser=float
        ) 
        self.add_parameter(
            name='sigout_range',
            label='Signal output range',
            unit='V',
            get_cmd=self._get_sigout_range,
            get_parser=float,
            set_cmd=self._set_sigout_range,
            vals=vals.Enum(0.01, 0.1, 1, 10)
        )
        self.add_parameter(
            name='sigout_offset',
            label='Signal output offset',
            unit='V',
            get_cmd=self._get_sigout_offset,
            get_parser=float,
            set_cmd=self._set_sigout_offset,
            vals=vals.Numbers(-1, 1),
            docstring='Multiply by sigout_range to get actual offset voltage.'
        )

        single_values = (('x', 'Demodulated x', 'V'),
                    ('y', 'Demodulated y', 'V') )

        for name, unit, label in single_values :
            self.add_parameter( f'demod{self.demod}_{name}',
                    unit=unit,
                    label=label,
                    get_cmd = partial( self._single_get, name )
            )
        self.add_parameter(
                name=f'demod{self.demod}_theta',
                label=f'Demodulated theta'+ str(self.demod),
                unit='deg',
                get_cmd= self._get_theta,
                get_parser=float
            )

        #### Parameters for sweeping
        sweeper = self.daq.sweep()
        sweeper.set("device", self.dev_id)
        ### different ones?!
        sweeper.set("gridnode", f"oscs/{self.sigout}/freq") ### Set the sweeping parameter
        self.sweeper = sweeper
        # do an initial trigger for snapshot

        sweeper_params = ( ( 'samplecount', '', 'Points' ),
                ( 'start', 'Hz', 'Start frequency' ),
                ('stop', 'Hz', 'Stop frequency' ),
                ('xmapping', '', 'X scale as log or linear'),
                ('bandwidthoverlap', '', 'Bandwidth Overlap') )

        for namex, unit, label in sweeper_params :
            self.add_parameter( f'sweeper_{namex}',
                    unit=unit,
                    label=label,
                    set_cmd = partial( self.sweeper.set, namex ),
                    get_cmd = partial( self._sweeper_get, namex )
            )

        self.add_parameter( 'trace_frequency',
                unit='Hz',
                label= 'Frequency',
                snapshot_value=False,
                get_cmd= lambda : self.sweeper_samples['frequency'],
                vals=vals.Arrays(shape=(self.sweeper_samplecount,))
            )

        self.add_parameter( 'averaging',
                unit='npts',
                label= 'Averaging',
                set_cmd = partial( self.sweeper.set, 'averaging/sample' ),
                get_cmd = partial( self._sweeper_get, 'averaging/sample' )
            )  
  
        self.auto_trigger = False 

        for p, units in ( ('r', 'dB'), ('x','dB'), ('y','dB'),('phase', 'rad') ) :
            self.add_parameter( f'trace_{p}',
                    unit= units,
                    label= p,
                    parameter_class = ParameterWithSetpoints,
                    setpoints = ( self.trace_frequency,),
                    get_cmd= partial(self._get_sweep_param, p ),
                    vals=vals.Arrays(shape=(self.sweeper_samplecount,))
                )
  
        for i in range(6, num_sigout_mixer_channels):
            self.add_parameter(
                name=f'sigout_enable{i}',
                label=f'Signal output mixer {i} enable',
                get_cmd=lambda mixer_channel=i: self._get_sigout_enable(mixer_channel),
                get_parser=float,
                set_cmd=lambda amp, mixer_channel=i: self._set_sigout_enable(mixer_channel, amp),
                vals=vals.Enum(0,1,2,3),
                docstring="""\
                0: Channel off (unconditionally)
                1: Channel on (unconditionally)
                2: Channel off (will be turned off on next change of sign from negative to positive)
                3: Channel on (will be turned on on next change of sign from negative to positive)
                """
            )
            self.add_parameter(
                name=f'sigout_amplitude{i}',
                label=f'Signal output mixer {i} amplitude',
                unit='Gain',
                get_cmd=lambda mixer_channel=i: self._get_sigout_amplitude(mixer_channel),
                get_parser=float,
                set_cmd=lambda amp, mixer_channel=i: self._set_sigout_amplitude(mixer_channel, amp),
                vals=vals.Numbers(-1, 1),
                docstring='Multiply by sigout_range to get actual output voltage.'
            )
    
    def _sweeper_get( self, name ) :
        """ wrap zi sweeper.get
        """
        return self.sweeper.get( name )[name][0]

    def _single_get(self, name):
        path = f'/{self.dev_id}/demods/{self.demod}/sample/'
        return self.daq.getSample(path)[name][0]


    def _get_sweep_param(self, param, fr=True):
        if self.auto_trigger :
            self.trigger_sweep()

        if param is 'phase' :
            values = self.sweeper_samples[param]
        else :
            # detect which node we are sweeping with
            amplitude = self._get_sigout_amplitude(self.sigout+6) / ( 2 * np.sqrt(2) ) # normalization factor for vpp 2x fudge
            values = 20 * np.log10( self.sweeper_samples[param]/amplitude )

        return values

    def _get_theta(self):
        path = f'/{self.dev_id}/demods/{self.demod}/sample/'
        theta = np.arctan(self.daq.getSample(path)['y']/self.daq.getSample(path)['x'])*180/np.pi
        return theta

    def trigger_sweep(self):
        sweeper = self.daq.sweep()
        #sweeper = self.sweeper
        sweeper.set('scan', 0) ### Sequenctial sweep
        sweeper.set("bandwidthcontrol", 2) ### Bandwidth control: Auto
        sweeper.set('maxbandwidth', 100) ### Max demodulation bandwidth
        path = f"/{self.dev_id}/demods/{self.demod}/sample"
        sweeper.set("start", self.sweeper_start())
        sweeper.set("stop", self.sweeper_stop())
        sweeper.set("samplecount", self.sweeper_samplecount())
        #sweeper.set()
        sweeper.subscribe(path)
        sweeper.execute()

        ### Wait until measurement is done 
        start_t = time.time()
        timeout = 60  # [s]
        while not sweeper.finished():  # Wait until the sweep is complete, with timeout.
            time.sleep(1)
            progress = sweeper.progress()
            if (time.time() - start_t) > timeout:
                print("\nSweep still not finished, forcing finish...")
                sweeper.finish()
        print("")
        data = sweeper.read(True)
        self.sweeper_samples = data[path][0][0]
        sweeper.unsubscribe(path) ### Unsubscribe from the signal path



    def _get_data(self, poll_length=0.1) -> float:
        path = f'/{self.dev_id}/demods/{self.demod}/sample'
        self.daq.unsubscribe("*")
        poll_timeout = 500  # [ms]
        poll_flags = 0
        poll_return_flat_dict = True
        self.daq.sync()
        self.daq.subscribe(path)
        data = self.daq.poll(poll_length, poll_timeout, poll_flags, poll_return_flat_dict)
        self.daq.unsubscribe("*")
        return data

    def readout(self):
        path = f'/{self.dev_id}/demods/{self.demod}/sample'
        data = self._get_data()
        sample = data[path]
        X = sample['x']
        Y = sample['y']
        clockbase = float(self.daq.getInt(f'/{self.dev_id}/clockbase'))
        t = (sample['timestamp'] - sample['timestamp'][0]) / clockbase 
        return (X, Y, t)


    def _get_phase(self) -> float:
        path = f'/{self.dev_id}/demods/{self.demod}/phaseshift/'
        return self.daq.getDouble(path)

    def _set_phase(self, phase: float) -> None:
        path = f'/{self.dev_id}/demods/{self.demod}/phaseshift/'
        self.daq.setDouble(path, phase)
        
    def _get_gain(self, channel: str) -> float:
        path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/scale/'
        return self.daq.getDouble(path)

    def _set_gain(self, gain: float, channel: str) -> None:
        path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/scale/'
        self.daq.setDouble(path, gain)

    def _get_offset(self, channel: str) -> float:
        path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/offset/'
        return self.daq.getDouble(path)

    def _set_offset(self, offset: float, channel: str) -> None:
        path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/offset/'
        self.daq.setDouble(path, offset)

    def _get_output_value(self, channel: str) -> float:
        path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/value/'
        return self.daq.getDouble(path)

    def _get_output_select(self, channel: str) -> str:
        path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/outputselect/'
        idx = self.daq.getInt(path)
        return self.OUTPUT_MAPPING[idx]

    def _set_output_select(self, channel: str) -> None:
        path = f'/{self.dev_id}/auxouts/{self.auxouts[channel]}/outputselect/'
        keys = list(self.OUTPUT_MAPPING.keys())
        idx = keys[list(self.OUTPUT_MAPPING.values()).index(channel)]
        self.daq.setInt(path, idx)

    def _get_time_constant(self) -> float:
        path = f'/{self.dev_id}/demods/{self.demod}/timeconstant/'
        return self.daq.getDouble(path)

    def _set_time_constant(self, tc: float) -> None:
        path = f'/{self.dev_id}/demods/{self.demod}/timeconstant/'
        self.daq.setDouble(path, tc)

    def _get_sigout_range(self) -> float:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/range/'
        return self.daq.getDouble(path)

    def _set_sigout_range(self, rng: float) -> None:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/range/'
        self.daq.setDouble(path, rng)

    def _get_sigout_offset(self) -> float:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/offset/'
        range = self._get_sigout_range()
        return self.daq.getDouble(path)*range

    def _set_sigout_offset(self, offset: float) -> None:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/offset/'
        range = self._get_sigout_range()
        return self.daq.setDouble(path, offset/range)

    def _get_sigout_amplitude(self, mixer_channel: int) -> float:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/amplitudes/{mixer_channel}/'
        range = self._get_sigout_range()
        return self.daq.getDouble(path)*range

    def _set_sigout_amplitude(self, mixer_channel: int, amp: float) -> None:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/amplitudes/{mixer_channel}/'
        range = self._get_sigout_range()
        return self.daq.setDouble(path, amp/range)

    def _get_sigout_enable(self, mixer_channel: int) -> int:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/enables/{mixer_channel}/'
        return self.daq.getInt(path)

    def _set_sigout_enable(self, mixer_channel: int, val: int) -> None:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/enables/{mixer_channel}/'
        self.daq.setInt(path, val)

    def _get_frequency(self) -> float:
        path = f'/{self.dev_id}/demods/{self.demod}/freq/'
        return self.daq.getDouble(path)

    def _set_frequency(self, freq) -> float:
        osc_index = 0
        return self.daq.set([["/%s/oscs/%d/freq" % (self.dev_id, osc_index), freq]])

    def sample(self) -> dict:
        path = f'/{self.dev_id}/demods/{self.demod}/sample/'
        return self.daq.getSample(path)
        
""" 
    def trigger_sweep(self):
        sweeper = self.daq.sweep()
        # sweeper.set("device", self.dev_id)
        # ### different ones?!
        # sweeper.set("gridnode", f"oscs/{0}/freq") ### Set the sweeping parameter
        sweeper = self.sweeper
        # sweeper.set("start", self.sweeper_start() )
        # sweeper.set("stop", self.sweeper_stop() )
        # sweeper.set('samplecount', self.sweeper_samplecount() )
        # sweeper.set("xmapping", 1) ### Logarithmic sweep
        sweeper.set('scan', 0) ### Sequenctial sweep
        sweeper.set("bandwidthcontrol", 2) ### Bandwidth control: Auto
        sweeper.set('maxbandwidth', 100) ### Max demodulation bandwidth
        #sweeper.set('bandwidthoverlap', 0) ### No bandwidth overlap

        # ### Number of averaging for each sweep point
        # sweeper.set('averaging/sample', 20)
        path = f"/{self.dev_id}/demods/{self.demod}/sample"

        sweeper.subscribe(path)
        ### Start measurement
        sweeper.execute()

        ### Wait until measurement is done 
        start_t = time.time()
        timeout = 60  # [s]
        #print("Will measure", self.sweeper_samplecount.get_latest(), "sweep pointss...")
        while not sweeper.finished():  # Wait until the sweep is complete, with timeout.
            time.sleep(1)
            progress = sweeper.progress()
            #print(f"Sweep progress: {progress[0]:.2%}.", end="\n")
            if (time.time() - start_t) > timeout:
                print("\nSweep still not finished, forcing finish...")
                sweeper.finish()
        print("")
        data = sweeper.read(True)  
        self.samples = data[path][0][0]
        sweeper.unsubscribe(path) ### Unsubscribe from the signal path
        # sweeper.finish() ### Finish the nodule
        # sweeper.clear() ### Delete the module
        #frequency = samples['frequency']
        #amplitude = samples['r']
        #phase = samples['phase']
 """