from typing import Dict, List, Optional, Sequence, Any, Union
from functools import partial
import numpy as np
import logging

from py import process
log = logging.getLogger(__name__)

import time
import matplotlib.pyplot as plt
import numpy as np

import zhinst.utils
import qcodes as qc
from qcodes.instrument.base import Instrument
from qcodes.instrument import InstrumentChannel
import qcodes.utils.validators as vals

from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter

from qcodes.dataset.measurements import Measurement, res_type, DataSaver
from qcodes.instrument.specialized_parameters import ElapsedTimeParameter

class HF2LIDemod(InstrumentChannel):
    """
    HF2LI demod
    """
    def __init__(self, parent: Instrument, name: str, demod : str) -> None:
        """
        Args:
            parent: The Instrument instance to which the channel is
                to be attached (HF2LI).
            name: The 'colloquial' name of the channel
            demod: name for ZI to look up
        """

        super().__init__(parent, name)
        self.demod = demod
        self.dev_id = self.parent.dev_id
        self.daq = self.parent.daq
        # self.model = self._parent.model
        
        if int(demod) in range(6): # x, y, theta only for first 5 demods 
            single_values = (('x', 'Demodulated x', 'V'),
                        ('y', 'Demodulated y', 'V') )
            
            

            for name, unit, label in single_values :
                self.add_parameter( f'{name}',
                        unit=unit,
                        label=label,
                        get_cmd = partial( self._single_get, name )
                )

            self.add_parameter(
                    name=f'theta',
                    label=f'Demodulated theta'+ str(self.demod),
                    unit='deg',
                    get_cmd= self._get_theta,
                    get_parser=float
                )
            
            self.add_parameter(
                name='phase',
                label='Phase',
                unit='deg',
                get_cmd=self._get_phase,
                get_parser=float,
                set_cmd=self._set_phase,
                vals=vals.Numbers(-180,180)
            )

            demod_params = ( 
            ('timeconstant', 's'),
            ('order', ''),
            ('rate', '')
            )
            for param, unit in demod_params :
                self.add_parameter(
                        name=param,
                        label=param,
                        unit=unit,
                        get_cmd= partial( self._get_demod_param, param ),
                        set_cmd= partial( self._set_demod_param, param ),
                        get_parser=float
                    )
            # daq sweeper parameters    
            sweeper = self.daq.sweep()
            sweeper.set("device", self.dev_id)
            sweeper.set("gridnode", f"oscs/{self.parent.sigout}/freq") ### Set the sweeping parameter
            self.sweeper = sweeper

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
                get_cmd= lambda : self.samples['grid'],
                vals=vals.Arrays(shape=(self.sweeper_samplecount,))
            )
            
            for p, units in ( ('r', 'dB'), ('x','dB'), ('y','dB'),('phase', 'deg') ) :
                self.add_parameter( f'trace_{p}',
                        unit= units,
                        label= p,
                        parameter_class = ParameterWithSetpoints,
                        setpoints = ( self.trace_frequency,),
                        get_cmd= partial(self._get_sweep_param, p ),
                        vals=vals.Arrays(shape=(self.sweeper_samplecount,))
                    )
                
            self.auto_trigger = False 
        
        self.add_parameter(
            name = 'osc',
            label = 'Oscillator',
            get_cmd = self._get_osc,
            get_parser = int,
            set_cmd = self._set_osc,
            vals = vals.Numbers(0,1)
        )

        self.add_parameter(
            name='frequency',
            label='Frequency',
            unit='Hz',
            get_cmd=self._get_frequency,
            set_cmd=self._set_frequency,
            get_parser=float
        ) 

        

    def _get_frequency(self) -> float:
        """
        get frequency by looking up oscillator 
        """
        osc_index = self.osc()
        path = f'/{self.dev_id}/oscs/{osc_index}/freq/'
        return self.daq.getDouble(path)
    
    def _set_frequency(self, freq) -> float:
        """
        set frequency by looking up oscillator 
        """
        osc_index = self.osc()
        return self.daq.set([["/%s/oscs/%d/freq" % (self.dev_id, osc_index), freq]])

    def _get_osc(self):
        if self.demod in ['6','7']:
            return int(self.demod) - 6
        else:
            path = f'/{self.dev_id}/demods/{self.demod}/oscselect/'
            return self.daq.getInt(path)
    
    def _set_osc(self, value):
        if self.demod in ['6','7']:
            print('Cannot change oscillator for demod 6 or 7')
            return
        else:
            path = f'/{self.dev_id}/demods/{self.demod}/oscselect/'
            self.daq.setInt(path,value)

    def _single_get(self, name):
        """
        get a parameter. only works for demods 0-5.
        """
        path = f'/{self.dev_id}/demods/{self.demod}/sample/'
        return self.daq.getSample(path)[name][0]
    
    def _get_theta(self):
        """
        get theta. only works for demods 0-5. 
        """
        path = f'/{self.dev_id}/demods/{self.demod}/sample/'
        sample = self.daq.getSample(path)
        cmplx = sample['x'] + 1j*sample['y']
        return np.angle(cmplx)*180/np.pi
    
    def _get_phase(self) -> float:
        path = f'/{self.dev_id}/demods/{self.demod}/phaseshift/'
        return self.daq.getDouble(path)

    def _set_phase(self, phase: float) -> None:
        path = f'/{self.dev_id}/demods/{self.demod}/phaseshift/'
        self.daq.setDouble(path, phase)

    def _get_demod_param( self, param ) :
        """ get demod parameter
        Args:
            param: string parameter name. eg timeconstant\
        Returns:
            parameter value as a double
        """
        path = f'/{self.dev_id}/demods/{self.demod}/{param}/'
        return self.daq.getDouble(path)


    def _set_demod_param( self, param, value ) :
        """ set demod parameter
        Args:
            param: string parameter name. eg timeconstant\
        Returns:
            parameter value as a double
        """
        path = f'/{self.dev_id}/demods/{self.demod}/{param}/'
        self.daq.setDouble(path, value)

    def _sweeper_get( self, name ) :
        """ wrap zi sweeper.get
        """
        return self.sweeper.get( name )[name][0]
    
    def _get_sweep_param(self, param, fr=True):
        if self.auto_trigger :
            self.trigger_sweep()

        if param == 'phase' :
            values = (self.samples[param])*180/np.pi
        else :
            # detect which node we are sweeping with
            osc = self.osc()
            mixer = self.parent.sigout2mixer[osc]
            amplitude = self.parent._get_sigout_amplitude( mixer, osc ) / ( 2 * np.sqrt(2) ) # normalization factor for vpp 2x fudge
            values = 20 * np.log10( self.samples[param]/amplitude )

        return values

    def trigger_sweep(self):
        # sweeper = self.daq.sweep()
        #self.snapshot(update=True)
        sweeper = self.sweeper
        sweeper.set("device", self.dev_id)
        sweeper.set('gridnode', f'oscs/{self.osc()}/freq')
        sweeper.set('scan', 0) ### Sequenctial sweep
        sweeper.set("bandwidthcontrol", 0) ### Bandwidth control: Auto
        #sweeper.set('maxbandwidth', 100) ### Max demodulation bandwidth
        sweeper.set('settling/inaccuracy', 1.0e-08)
        path = f"/{self.dev_id}/demods/{self.demod}/sample"
        sweeper.set("start", self.sweeper_start())
        sweeper.set("stop", self.sweeper_stop())
        sweeper.set("samplecount", self.sweeper_samplecount()) 
        #sweeper.set()
        self.timeconstant(self.timeconstant())
        sweeper.subscribe(path)
        sweeper.execute()

        ### Wait until measurement is done 
        start_t = time.time()
        timeout = 6000  # [s]
        while not sweeper.finished():  # Wait until the sweep is complete, with timeout.
            time.sleep(1)
            progress = sweeper.progress()
            if (time.time() - start_t) > timeout:
                print("\nSweep still not finished, forcing finish...")
                sweeper.finish()
        data = sweeper.read(True)
        self.samples = data[path][0][0]
        sweeper.unsubscribe(path) ### Unsubscribe from the signal path

class HF2LI(Instrument):
    """
    Qcodes driver for Zurich Instruments HF2LI lockin amplifier.

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
        sigout2mixer: mapping from sigout to mixers. For default HF2LI {0:6, 1:7}
        num_sigout_mixer_channels: Number of mixer channels to enable on the sigouts. Default: 1.
    """
    OUTPUT_MAPPING = {-1: 'manual', 0: 'X', 1: 'Y', 2: 'R', 3: 'Theta'}
    def __init__(self, name: str, device: str, demod: int, sigout: int,
            auxouts: Dict[str, int], 
            sigout2mixer : Dict[ int, int ]={0:6, 1:7},
            num_sigout_mixer_channels: int=1, 
            **kwargs) -> None:

        super().__init__(name, **kwargs)
        instr = zhinst.utils.create_api_session(device, 1 )#, 
            #required_devtype='HF2LI') #initializes the instrument
        self.daq, self.dev_id, self.props = instr
        self.demod = demod
        self.sigout = sigout
        self.auxouts = auxouts
        log.info(f'Successfully connected to {name}.')
        self.sigout2mixer = sigout2mixer

        for ch in self.auxouts: #NOT MIGRATED
            self.add_parameter( #NOT MIGRATED
                name=ch,
                label=f'Scaled {ch} output value',
                unit='V',
                get_cmd=lambda channel=ch: self._get_output_value(channel),
                get_parser=float,
                docstring=f'Scaled and demodulated {ch} value.'
            )
            # self.add_parameter( #NOT ADDED 
            #     name=f'gain_{ch}',
            #     label=f'{ch} output gain',
            #     unit='V/Vrms',
            #     get_cmd=lambda channel=ch: self._get_gain(channel),
            #     get_parser=float,
            #     set_cmd=lambda gain, channel=ch: self._set_gain(gain, channel),
            #     vals=vals.Numbers(),
            #     docstring=f'Gain factor for {ch}.'
            # )
            self.add_parameter( #NOT MIGRATED
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
            
        self.add_parameter( #NOT MIGRATED
            name='ext_clk',
            label='External Clock',
            unit='',
            set_cmd=self._set_ext_clk,
            get_cmd=self._get_ext_clk,
            vals=vals.Bool()
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
            snapshot_value=True,
            set_cmd=self._set_sigout_offset,
            get_cmd=self._get_sigout_offset,
            vals=vals.Numbers(-1, 1),
            docstring='Multiply by sigout_range to get actual offset voltage.'
        )

        for output, mixer_channel in sigout2mixer.items():
        # for i in range(6, num_sigout_mixer_channels):
            self.add_parameter(
                name=f'sigout_enable{mixer_channel}',
                label=f'Signal output mixer {mixer_channel} enable',
                get_cmd=lambda : self._get_sigout_enable(mixer_channel, output),
                get_parser=float,
                set_cmd=lambda amp : self._set_sigout_enable(mixer_channel, output, amp),
                vals=vals.Enum(0,1,2,3),
                docstring="""\
                0: Channel off (unconditionally)
                1: Channel on (unconditionally)
                2: Channel off (will be turned off on next change of sign from negative to positive)
                3: Channel on (will be turned on on next change of sign from negative to positive)
                """
            )
            self.add_parameter(
                name=f'sigout_amplitude{mixer_channel}',
                label=f'Signal output mixer {mixer_channel} amplitude',
                unit='Gain',
                get_cmd=partial( self._get_sigout_amplitude, mixer_channel, output ),
                get_parser=float,
                set_cmd=partial( self._set_sigout_amplitude, mixer_channel, output ),
                vals=vals.Numbers(-10, 10),
                docstring='Multiply by sigout_range to get actual output voltage.'
            )

        demods = [str(i) for i in range(8)]
        for d in demods:
            d_name = f'demod_{d}'
            demod = HF2LIDemod(self, d_name, d)
            self.add_submodule(d_name, demod)

    def _sweeper_get( self, name ) :
        """ wrap zi sweeper.get
        """
        return self.sweeper.get( name )[name][0]

    # def _single_get(self, name):
    #     path = f'/{self.dev_id}/demods/{self.demod}/sample/'
    #     return self.daq.getSample(path)[name][0]
    
    def _set_ext_clk(self, val):
        """ set external 10 MHz clock
        """
        path = f'/{self.dev_id}/system/extclk'
        self.daq.setInt(path, int(val) )

    def _get_ext_clk( self ):
        """ get external 10 MHz clock as bool
        """
        path = f'/{self.dev_id}/system/extclk'
        val = self.daq.getInt( path )
        return bool( val )

    # def _get_sweep_param(self, param, fr=True):
    #     if self.auto_trigger :
    #         self.trigger_sweep()

    #     if param == 'phase' :
    #         values = (self.samples[param])*180/np.pi
    #     else :
    #         # detect which node we are sweeping with
    #         osc = self.osc
    #         mixer = self.sigout2mixer[osc]
    #         amplitude = self._get_sigout_amplitude( mixer, osc ) / ( 2 * np.sqrt(2) ) # normalization factor for vpp 2x fudge
    #         values = 20 * np.log10( self.samples[param]/amplitude )

    #     return values

    
        
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

    def _get_sigout_range(self, sigout=None ) -> float:
        if sigout is None :
            sigout = self.sigout
        path = f'/{self.dev_id}/sigouts/{sigout}/range/'
        return self.daq.getDouble(path)

    def _set_sigout_range(self, rng: float, sigout=None ) -> None:
        if sigout is None :
            sigout = self.sigout       
        path = f'/{self.dev_id}/sigouts/{sigout}/range/'
        self.daq.setDouble(path, rng)
    
    def _set_dc_range(self, rng: float) -> None:
        path = f'/dev1792/sigouts/1/range/'
        self.daq.setDouble(path, rng)

    def _get_dc_range(self) -> float:
        path = f'/dev1792/sigouts/1/range/'
        return self.daq.getDouble(path)
    
    # def _get_dc_offset(self) -> float:
    #     path = f'/dev1792/sigouts/1/offset/'
    #     range = self._get_dc_range()
    #     return self.daq.getDouble(path)*range

    # def _set_dc_offset(self, offset: float) -> None:
    #     path = f'/dev1792/sigouts/1/offset/'
    #     range = self._get_dc_range()
    #     return self.daq.setDouble(path, offset/range)

    def _get_sigout_offset(self) -> float:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/offset/'
        range = self._get_sigout_range()
        return self.daq.getDouble(path)*range

    def _set_sigout_offset(self, offset: float) -> None:
        path = f'/{self.dev_id}/sigouts/{self.sigout}/offset/'
        range = self._get_sigout_range()
        return self.daq.setDouble(path, offset/range)

    def _get_sigout_amplitude(self, mixer_channel: int, sigout:int ) -> float:
        path = f'/{self.dev_id}/sigouts/{sigout}/amplitudes/{mixer_channel}/'
        range = self._get_sigout_range(sigout=sigout)
        return self.daq.getDouble(path)*range

    def _set_sigout_amplitude(self, mixer_channel: int, sigout:int, amp: float) -> None:
        path = f'/{self.dev_id}/sigouts/{sigout}/amplitudes/{mixer_channel}/'
        range = self._get_sigout_range(sigout=sigout)
        return self.daq.setDouble(path, amp/range)

    def _get_sigout_enable(self, mixer_channel: int, sigout: int ) -> int:
        path = f'/{self.dev_id}/sigouts/{sigout}/enables/{mixer_channel}/'
        return self.daq.getInt(path)

    def _set_sigout_enable(self, mixer_channel: int, sigout: int, val: int) -> None:
        path = f'/{self.dev_id}/sigouts/{sigout}/enables/{mixer_channel}/'
        self.daq.setInt(path, val)

    def sample(self) -> dict:
        path = f'/{self.dev_id}/demods/{self.demod}/sample/'
        return self.daq.getSample(path)
        
    def ask(self,arg) :
        """" hacking in an ask method
        """
        if arg == "*IDN?" :
            return self.dev_id
        else :
            raise ValueError(f"I don't understand {arg}")