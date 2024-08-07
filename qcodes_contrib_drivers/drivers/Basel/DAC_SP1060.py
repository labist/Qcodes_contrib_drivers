import time
import pyvisa as visa
import warnings
import logging
from functools import partial
from typing import Sequence, Any
from qcodes import VisaInstrument, InstrumentChannel, ChannelList
from qcodes.instrument.channel import MultiChannelInstrumentParameter
from qcodes.utils import validators as vals
from qcodes.parameters import Parameter


log = logging.getLogger(__name__)

class SP1060Exception(Exception):
    pass


class SP1060Reader(object):
    def _vval_to_dacval(self, vval):
        """
        Convert voltage to DAC value 
        dacval=(Vout+10)*838860.75 
        """
        try:
            dacval = int((float(vval)+10)*838860.75 )
            return dacval
        except:
            pass

    def _dacval_to_vval(self, dacval):
        """
        Convert DAC value to voltage
        Vout=(dacval/838860.75 )–10
        """
        try:
            vval = round((int(dacval.strip(),16)/float(838860.75))-10, 6)
            return vval
        except:
            pass


   
       
        
    #(parser for state)


    #def (parser for shape)


    #def (parser for mode)

   

class SP1060MultiChannel(MultiChannelInstrumentParameter, SP1060Reader):
    def __init__(self, channels:Sequence[InstrumentChannel], param_name: str, *args: Any, **kwargs: Any):
        super().__init__(channels, param_name, *args, **kwargs)
        self._channels = channels
        self._param_name = param_name
        
        def get_raw(self):
            output = tuple(chan.parameters[self._param_name].get() for chan in self._channels)
            return output
        
        def set_raw(self, value):
            for chan in self._channels:
                chan.volt.set(value)
            
    
class SP1060Channel(InstrumentChannel, SP1060Reader):
   
    def __init__(self, parent, name, channel, min_val=-10, max_val=10, 
                 voltage_post_delay=0.02, voltage_step=0.01):
        super().__init__(parent, name)
        
        # validate channel number
        self._CHANNEL_VAL = vals.Ints(1,24)
        self._CHANNEL_VAL.validate(channel)
        self._channel = channel

        # limit voltage range
        self._volt_val = vals.Numbers(min(min_val, max_val), max(min_val, max_val))
        
        self.volt: Parameter = self.add_parameter('volt',
                           label = 'C {}'.format(channel),
                           unit = 'V',
                           set_cmd = partial(self._parent._set_voltage, channel),
                           set_parser = self._vval_to_dacval,
                           post_delay = voltage_post_delay,
                           step = voltage_step,
                           get_cmd = partial(self._parent._read_voltage, channel),
                           vals = self._volt_val 
                           )

        self.status: Parameter = self.add_parameter('status',
                            label = f'chan{channel} output status',
                            set_cmd = f"{channel} {{}}",
                            get_cmd = f'{channel} S?',
                            vals = vals.Enum('ON', 'OFF')
                            )
        
        self.registered: Parameter = self.add_parameter('registered',
                            label = f'chan{channel} registered value',
                            unit = 'V', 
                            get_cmd = f'{channel} VR?',
                            get_parser = self.parent._dacval_to_vval,
                            vals = self._volt_val
                            )

        self.bandwidth: Parameter = self.add_parameter('bandwidth',
                            label = f'chan{channel} Bandwidth',
                            set_cmd = f"{channel} {{}}",
                            get_cmd = f'{channel} BW?',
                            vals = vals.Enum('LBW', 'HBW')
                            )
        
        self.mode: Parameter = self.add_parameter('mode',
                            label = f'chan{channel} mode',
                            get_cmd = f'{channel} M?',
                            vals = vals.Enum('ERR', 'DAC', 'SYN', 'RMP', 'AWG', '---')
                            )
    
    """    honestly leave as is
    def _mode_parser(self, modeval):
        valdict = {'ERR':'Error',
                   'DAC':'Converted',
                   'SYN':'Registered Nominal, DAC values are registered and apllied once SYNC signal is received',
                   'RMP':'RAMP',
                   'AWG':'AWG',
                   '---':'BlockedChannel not available (board likely reserved for AWG), writing not allowed'
                   }
        return valdict[modeval]
    """

class RampGenerator(InstrumentChannel, SP1060Reader):
    
    """
     Defines class of Ramp generators
    
     Defined here is the general class for ramp generators
     to have all of their necessary commands as attributes
     to be called later within the SP1060 class. This way,
     one can just do dac.ramp[A/B/C/D].[attribute name]
     to call each command.

     Attributes:
        control : str
            Takes in a string to start, stop, or hold a ramp
            generator
        
        state : str
            Outputs whether the ramp gen is idle, ramping up,
            ramping down, or holding
        
        ava : boolean
            Returns if the selected channel for the ramp is
            available (returns False if another generator is
            currently using the channel)

        selchan : int
            Set/get the channel to receive the ramp generator's
            signal. Not restricted to either lower or higher board
        
        start : float
            Set/get the starting voltage
        
        stop : float
            Set/get the ending voltage (either peak or stopping)

        period : float
            Set/get the time to complete one cycle in seconds

        shape : str
            Set/get the shape of a cycle, either sawtooth or triangle

        cycles : int
            Set/get the  number of cycles to run. If 0 cycles is
            selected, the ramp generator will run infinitely unless
            told to stop

        mode : str
            Set/get the mode of the ramp generator, either ramp mode
            or step mode (step mode is really only used for 2D-scans)

        cycles_done : int
            Returns the cycles completed by the ramp generator. Retains
            value after ramp generator stops

        steps_done : int
            Returns the steps completed by the ramp generator so far
            in a single cycle. Does not retain its value after the
            ramp generator starts a new cycle or finishes all of its
            programmed cycles

        step : float
            Returns the step value of the slope as internally
            calculated with the set period, starting/ending voltage,
            and shape

        spc : int
            Returns the steps per cycle as internally calculated

    """
    
    def __init__(self, parent, name, generator, min_val=-10, max_val=10, num_chans = 24):
        super().__init__(parent, name)

        # first allow the numbering of the generators
        self._GENERATOR_VAL = vals.Enum('a', 'b', 'c', 'd')
        self._GENERATOR_VAL.validate(generator)
        self._generator = generator

        
        
        # limit voltage range
        self._volt_val = vals.Numbers(min(min_val, max_val), max(min_val, max_val))

        #then list all of their attributes
        self.control: Parameter = self.add_parameter('control',
                                label = f'{name} control',
                                set_cmd = self._set_control,
                                vals = vals.Enum('START', 'HOLD', 'STOP')
                                )
        
        self.state: Parameter = self.add_parameter('state',
                                label = f'{name} state',
                                get_cmd = f'C RMP-{generator} S?',
                                get_parser = self._state_get_parser
                                )
        
        self.ava: Parameter = self.add_parameter('ava',
                                label = f'{name} ava',
                                get_cmd = f'C RMP-{generator} AVA?',
                                get_parser = bool,
                                vals = vals.Bool()
                                )
        
        self.selchan: Parameter = self.add_parameter('selchan',
                                label = f'{name} selchan',
                                set_cmd = f"C RMP-{generator} CH {{}}",
                                get_cmd = f'C RMP-{generator} CH?',
                                get_parser = int,
                                vals = vals.Numbers(min(1, num_chans), max(1, num_chans))
                                )
        
        self.start: Parameter = self.add_parameter('start',
                                label = f'{name} start',
                                unit = 'V',
                                set_cmd = f"C RMP-{generator} STAV {{}}",
                                get_cmd = f'C RMP-{generator} STAV?',
                                get_parser = float,
                                vals = self._volt_val
                                )
        
        self.stop: Parameter = self.add_parameter('stop',
                                label = f'{name} stop',
                                unit = 'V',
                                set_cmd = f"C RMP-{generator} STOV {{}}",
                                get_cmd = f'C RMP-{generator} STOV?',
                                get_parser = float,
                                vals = self._volt_val
                                )

        self.period: Parameter = self.add_parameter('period',
                                label = f'{name} period',
                                unit = 's',
                                set_cmd = f"C RMP-{generator} RT {{}}",
                                get_cmd = f'C RMP-{generator} RT?',
                                get_parser = float,
                                vals = vals.Numbers(0.05, 1000000)
                                )

        self.shape: Parameter = self.add_parameter('shape',
                                label = f'{name} shape',
                                set_cmd = f"C RMP-{generator} RS {{}}",
                                get_cmd = f'C RMP-{generator} RS?',
                                set_parser = self._shape_set_parser,
                                get_parser = self._shape_get_parser,
                                vals = vals.Enum('sawtooth', 'triangle')
                                )
        
        self.cycles: Parameter = self.add_parameter('cycles',
                                label = f'{name} cycles',
                                set_cmd = f"C RMP-{generator} CS {{}}",
                                get_cmd = f'C RMP-{generator} CS?',
                                get_parser = int,
                                vals = vals.Ints(0, 4000000000)
                                #selecting 0 -> runs until stopped by the user
                                )
        
        self.mode: Parameter = self.add_parameter('mode',
                                label = f'{name} mode',
                                set_cmd = f"C RMP-{generator} STEP {{}}",
                                get_cmd = f'C RMP-{generator} STEP?',
                                set_parser = self._mode_set_parser,
                                get_parser = self._mode_get_parser,
                                vals = vals.Enum('ramp', 'step')
                                #0 is selecting ramp, 1 is selecting step
                                )
        
        self.cycles_done: Parameter = self.add_parameter('cycles_done',
                                label = f'{name} cycles_done',
                                get_cmd = f'C RMP-{generator} CD?',
                                get_parser = int,
                                vals = vals.Ints(0, 4000000000)
                                )
        
        self.steps_done: Parameter = self.add_parameter('steps_done',
                                label = f'{name} steps_done',
                                get_cmd = f'C RMP-{generator} SD?',
                                get_parser = int,
                                vals = vals.Ints(0, 4000000000)
                                )
        
        self.step: Parameter = self.add_parameter('step',
                                label = f'{name} step',
                                unit = 'V',
                                get_cmd = f'C RMP-{generator} SSV?',
                                get_parser = float,
                                vals = vals.Numbers(-10, 10)
                                #is this based on min/max value or not?
                                )
        
        self.spc: Parameter = self.add_parameter('spc',
                                label = f'{name} spc',
                                get_cmd = f'C RMP-{generator} ST?',
                                get_parser = int,
                                vals = vals.Ints(10, 200000000)
                                )
        
    def _set_control(self, val):
        """
         Set control. Warn user if channel is not on
        Args:
            val: START/STOP/HOLD
        """
        # if channel is not on raise a warning
        chan_num = self.selchan()
        channel = self.parent.channels[chan_num-1]
        if channel.status() == 'OFF':
            #self.log.warning(f'Channel {chan_num} is off, ramping anyway.')
            #warnings.filterwarnings('default', 'you fucking moron, you buffoon, you menso')
            #import warnings
            #warnings.warn("you fucking moron, you buffoon, you menso")
            
            print(f'{chan_num} not on, ramping anyway')
            # self.log.warning(f'Channel {chan_num} is off, ramping anyway.')
        self.write(f"C RMP-{self._generator} {val}")
        
    
    """Various parsers for each attribute"""
    def _state_get_parser(self, stateval):
        naraco = {'0':' idle', '1':'rampup', '2':'rampdown', '3':'holding'}
        return naraco[stateval]
    
    def _shape_set_parser(self, shapeval):
        dict = {'sawtooth':0, 'triangle':1}
        return dict[shapeval]
    
    def _shape_get_parser(self, shapeval):
        cammie = {'0':'sawtooth', '1':'triangle'}
        return cammie[shapeval]

    def _mode_set_parser(self, modeval):
        dict = {'ramp':0, 'step':1}
        return dict[modeval]
    
    def _mode_get_parser(self, modeval):
        xof = {'0':'ramp', '1':'step'}
        return xof[modeval]


class AWG(InstrumentChannel, SP1060Reader):
    def __init__(self, parent, name, arbitrary_generator, num_chans = 24):
        super().__init__(parent, name)

        # first allow the numbering of the generators
        self._GENERATOR_VAL = vals.Enum('a', 'b', 'c', 'd')
        self._GENERATOR_VAL.validate(arbitrary_generator)
        self._arbitrary_generator = arbitrary_generator

        #now add some attributes
        ##### AWG functionality
        self.block: Parameter = self.add_parameter('block',
                                label = f'{name} block',
                                #set_cmd = self._block_set_parser,
                                #get_cmd = self._block_get_parser,
                                #MANUALLY PUT IN AS AB GROUP,CHANGE TO BE GENERAL
                                )

        self.control: Parameter = self.add_parameter('control',
                                label = f'{name} control',
                                set_cmd = f'C AWG-{arbitrary_generator} {{}}',
                                vals = vals.Enum('START', 'STOP')
                                )
        
        self.state: Parameter = self.add_parameter('state',
                                label = f'{name} state',
                                get_cmd = f'C AWG-{arbitrary_generator} S?',
                                get_parser = self._state_get_parser
                                )
        
        ##AWG Cycles-Done
        
        self.cycle_period: Parameter = self.add_parameter('cycle_period',
                                label = f'{name} cycle_period',
                                unit = 's',
                                get_cmd = f'C AWG-{arbitrary_generator} DP?',
                                get_parser = float,
                                vals = vals.Enum(20e-6, 1.36e8)
                                )
        
        self.ava: Parameter = self.add_parameter('ava',
                                label = f'{name} ava',
                                get_cmd = f'C AWG-{arbitrary_generator} AVA?',
                                get_parser = self._ava_get_parser
                                #do boolean for?
                                )
        
        self.selchan: Parameter = self.add_parameter('selchan',
                                label = f'{name} selchan',
                                set_cmd = f'C AWG-{arbitrary_generator} CH {{}}',
                                get_cmd = f'C AWG-{arbitrary_generator} CH?',
                                get_parser = int,
                                vals = vals.Ints(1, num_chans)
                                #FIX SO ONLY A,B CAN ACCESS 1-12, ETC
                                )
        
        ##AWG-Memory Size
        self.awgmem: Parameter = self.add_parameter('awgmem',
                                label = f'{name} awgmem',
                                set_cmd = f'C AWG-{arbitrary_generator} MS {{}}',
                                get_cmd = f'C AWG-{arbitrary_generator} MS?',
                                get_parser = int,
                                vals = vals.Ints(2,34000)
                                )
        
        self.cycles: Parameter = self.add_parameter('cycles',
                                label = f'{name} cycles',
                                set_cmd = f'C AWG-{arbitrary_generator} CS {{}}',
                                get_cmd = f'C AWG-{arbitrary_generator} CS?',
                                get_parser = int,
                                vals = vals.Numbers(0, 4e9)
                                )
        
        ##AWG External Trigger Mode

        ##AWG Clock-Period
        self.awgclock: Parameter = self.add_parameter('awgclock',
                                label = f'{name} awgclock',
                                unit = 'microseconds',
                                set_cmd = f'C AWG-AB CP {{}}',
                                get_cmd = f'C AWG-AB CP?',
                                get_parser = int,
                                vals = vals.Numbers(10,4e9)
                                #MAKE GENERAL FOR EACH BOARD, PUT IN AB FOR NOW1
                                )

        ##AWG 1 MHz Clock Reference




        ##### SWG functionality
        self.mode: Parameter = self.add_parameter('mode',
                                label = f'{name} mode',
                                set_cmd = f'C SWG MODE {{}}',
                                get_cmd = f'C SWG MODE?',
                                set_parser = self._mode_set_parser,
                                get_parser = self._mode_get_parser
                                )
        
        self.wave: Parameter = self.add_parameter('wave',
                                label = f'{name} wave',
                                set_cmd = f'C SWG WF {{}}',
                                get_cmd = f'C SWG WF?',
                                set_parser = self._wave_set_parser,
                                get_parser = self._wave_get_parser
                                )
        
        self.freq: Parameter = self.add_parameter('freq',
                                label = f'{name} freq',
                                unit = 'Hz',
                                set_cmd = f'C SWG DF {{}}',
                                get_cmd = f'C SWG DF?',
                                get_parser = float,
                                vals = vals.Numbers(0.001, 10000)
                                )
        
        self.clockset: Parameter = self.add_parameter('clockset',
                                label = f'{name} clockset',
                                set_cmd = f'C SWG ACLK {{}}',
                                get_cmd = f'C SWG ACLK?',
                                set_parser = self._clockset_set_parser,
                                get_parser = self._clockset_get_parser
                                )
        
        self.amp: Parameter = self.add_parameter('amp',
                                label = f'{name} amp',
                                unit = 'V',
                                set_cmd = f'C SWG AMP {{}}',
                                get_cmd = f'C SWG AMP?',
                                get_parser = float,
                                vals = vals.Numbers(-50, 50)
                                )
        
        self.offset: Parameter = self.add_parameter('offset',
                                label = f'{name} offset',
                                unit = 'V',
                                set_cmd = f'C SWG DCV {{}}',
                                get_cmd = f'C SWG DCV?',
                                get_parser = float,
                                vals = vals.Numbers(-10, 10)
                                )
        
        self.phase: Parameter = self.add_parameter('phase',
                                label = f'{name} phase',
                                unit = 'Degrees',
                                set_cmd = f'C SWG PHA {{}}',
                                get_cmd = f'C SWG PHA?',
                                get_parser = float,
                                vals = vals.Numbers(-360, 360)
                                )
        
        self.pulse: Parameter = self.add_parameter('pulse',
                                label = f'{name} pulse',
                                unit = '%',
                                set_cmd = f'C SWG DUC {{}}',
                                get_cmd = f'C SWG DUC?',
                                get_parser = float,
                                vals = vals.Numbers(0,100)
                                )
        
        ##Wave-Memory size
        self.swgmem: Parameter = self.add_parameter('swgmem',
                                label = f'{name} swgmem',
                                get_cmd = f'C SWG MS?',
                                get_parser = int,
                                vals = vals.Ints(10, 34000)
                                )

        ##Nearests AWG-Frequency
        self.closefreq: Parameter = self.add_parameter('closefreq',
                                label = f'{name} closefreq',
                                unit = 'Hz',
                                get_cmd = f'C SWG NF?',
                                get_parser = float,
                                vals = vals.Numbers(0.001, 10000)
                                )
        
        self.clip: Parameter = self.add_parameter('clip',
                                label = f'{name} clip',
                                get_cmd = f'C SWG CLP?',
                                get_parser = self._clip_get_parser
                                #do boolean here too?
                                )
        
        ##SWG/AWG Clock-Period
        self.swgclock: Parameter = self.add_parameter('swgclock',
                                label = f'{name} swgclock',
                                unit = 'microseconds',
                                get_cmd = f'C SWG CP?',
                                get_parser = int,
                                vals = vals.Ints(10, 4000000000)
                                )
        
        self.selwavemem: Parameter = self.add_parameter('selwavemem',
                                label = f'{name} selwavemem',
                                set_cmd = f'C SWG WMEM {{}}',
                                get_cmd = f'C SWG WMEM?',
                                set_parser = self._selwavemem_set_parser,
                                get_parser = self._selwavemem_get_parser
                                )

        self.selfunc: Parameter = self.add_parameter('selfunc',
                                label = f'{name} selfunc',
                                set_cmd = f'C SWG WFUN {{}}',
                                get_cmd = f'C SWG WFUN?',
                                set_parser = self._selfunc_set_parser,
                                get_parser = self._selfunc_get_parser
                                )

        ##No Linearization / Linearization
        self.lin: Parameter = self.add_parameter('lin',
                                label = f'{name} lin',
                                set_cmd = f'C SWG LIN {{}}',
                                get_cmd = f'C SWG LIN?',
                                set_parser = self._lin_set_parser,
                                get_parser = self._lin_get_parser
                                )

        self.apply: Parameter = self.add_parameter('apply',
                                label = f'{name} apply',
                                set_cmd = f'C SWG APPLY'
                                )
        
        """
        ### Wave Memory Functionality
        self.wmsize: Parameter = self.add_parameter('wmsize',
                                label = f'{name} wmsize',
                                get_cmd = f'C WAV-{}'
                                )

        self.wmclear:

        self.wmsave:

        self.wmlin: 

        self.wmtoawg:

        self.wmbusy: 

        """



        

    
    ### AWG functionality parsers
    """
    def _block_set_parser(self, val1, val2):
        val1, val2 = input(self.set_cmd()).split()
        dict1 = {'lower':'AB', 'higher':'CD'}
        self.write(f'C AWG-' + {dict1[val1]} + ' ONLY ' + val2)


        
    def _block_get_parser(self, blockval):
        dict = {'0':'No restrictions on other channels',
                '1':'Other channels on board cannot be used'}
        return dict[blockval]
    """

    def _state_get_parser(self, stateval):
        dict = {'0':'Idle',
                '1':'Running'
                }
        return dict[stateval]
    
    def _ava_get_parser(self, avaval):
        dict = {'0':'false',
                '1':'true'
                }
        return dict[avaval]
    
    
    
    ### SWG functionality parsers
    def _mode_set_parser(self, modeval):
        dict = {'generate':0, 'saved':1}
        return dict[modeval]
    
    def _mode_get_parser(self, modeval):
        dict = {'0':'generate',
                '1':'saved'
                }
        return dict[modeval]

    def _wave_set_parser(self, waveval):
        dict = {'sine':0,
                'triangle':1,
                'sawtooth':2,
                'ramp':3,
                'pulse':4,
                'fixedgaussian':5,
                'randomgaussian':6,
                'dc':7
                }
        return dict[waveval]
    
    def _wave_get_parser(self, waveval):
        dict = {'0':'sine',
                '1':'triangle',
                '2':'sawtooth',
                '3':'ramp',
                '4':'pulse',
                '5':'fixedgaussian',
                '6':'randomgaussian',
                '7':'dc'
                }
        return dict[waveval]
    
    def _clockset_set_parser(self, clockval):
        dict = {'keep':0,
                'adapt':1
                }
        return dict[clockval]
    
    def _clockset_get_parser(self, clockval):
        dict = {'0':'keep',
                '1':'adapt'
                }
        return dict[clockval]
    
    def _clip_get_parser(self, clipval):
        dict = {'0':'False',
                '1':'True'
                }
        return dict[clipval]
    
    def _selwavemem_set_parser(self, selwavememval):
        dict = {'a':0,
                'b':1,
                'c':2,
                'd':3
                }
        return dict[selwavememval]
    
    def _selwavemem_get_parser(self, selwavememval):
        dict = {'0':'a',
                '1':'b',
                '2':'c',
                '3':'d'
                }
        return dict[selwavememval]
    
    def _selfunc_set_parser(self, selfuncval):
        dict = {'copy':0,
                'startappend':1,
                'endappend':2,
                'startsum':3,
                'endsum':4,
                'startmult':5,
                'endmult':6,
                'startdivide':7,
                'enddivide':8
                }
        return dict[selfuncval]
    
    def _selfunc_get_parser(self, selfuncval):
        webster = {'0':'copy',
                   '1':'startappend',
                   '2':'endappend',
                   '3':'startsum',
                   '4':'endsum',
                   '5':'startmult',
                   '6':'endmult',
                   '7':'startdivide',
                   '8':'enddivide'
                   }
        return webster[selfuncval]
    
    def _lin_set_parser(self, linval):
        dict = {'false':0, 'true':1}
        return dict[linval]

    def _lin_get_parser(self, linval):
        dict = {'0':'false', '1':'true'}
        return dict[linval]
    
    """### Wave Memory functionality parsers"""




"""
#attempting to add subclasses to differentiate easily
class SWGFunctionality(AWG):
    def __init__(self, parent, name):
        super().__init__(parent, name)

        self.wave: Parameter = self.add_parameter('wave',
                                label = f'{name} wave',
                                set_cmd = f'C SWG WF {{}}',
                                get_cmd = f'C SWG WF?',
                                get_parser = self._wave_parser
                                )


    def _wave_parser(self, waveval):
        thisisadict = {'0':'Sine selected',
                       '1':'Triangle selected',
                       '2':'Sawtooth selected',
                       '3':'Ramp selected',
                       '4':'Pulse selected',
                       '5':'Gaussian noise (Fixed seed) selected',
                       '6':'Gaussian Noise (Random seed) selected',
                       '7':'DC-Voltage only selected'}
        return thisisadict[waveval]

"""

class SP1060(VisaInstrument, SP1060Reader):
    """
    QCoDeS driver for the Basel Precision Instruments SP1060 LNHR DAC
    https://www.baspi.ch/low-noise-high-resolution-dac
    """
    
    def __init__(self, name, address, min_val=-10, max_val=10, baud_rate=115200, 
                 voltage_post_delay=0.02, voltage_step=0.01, num_chans=24,**kwargs):
        """
        Creates an instance of the SP1060 24 channel LNHR DAC instrument.
        Args:
            name (str): What this instrument is called locally.
            port (str): The address of the DAC. For a serial port this is ASRLn::INSTR
                        where n is replaced with the address set in the VISA control panel.
                        Baud rate and other serial parameters must also be set in the VISA control
                        panel.
            min_val (number): The minimum value in volts that can be output by the DAC.
            max_val (number): The maximum value in volts that can be output by the DAC.
        """
        super().__init__(name, address, **kwargs)

        # Serial port properties
        handle = self.visa_handle
        handle.baud_rate = baud_rate
        handle.parity = visa.constants.Parity.none
        handle.stop_bits = visa.constants.StopBits.one
        handle.data_bits = 8
        handle.flow_control = visa.constants.VI_ASRL_FLOW_XON_XOFF
        handle.write_termination = '\r\n'
        handle.read_termination = '\r\n'

        # Create channels
        channels = ChannelList(self, 
                               "Channels", 
                               SP1060Channel, 
                               snapshotable = False,
                               multichan_paramclass = SP1060MultiChannel)
        self.num_chans = num_chans
        
        for i in range(1, 1+self.num_chans):
            channel = SP1060Channel(self, 'chan{:1}'.format(i), i, 
                                    voltage_post_delay=voltage_post_delay, 
                                    voltage_step=voltage_step,
                                    min_val = min_val,
                                    max_val = max_val)
            channels.append(channel)
            self.add_submodule('ch{:1}'.format(i), channel)
        channels.lock()
        self.add_submodule('channels', channels)
        
        
        #create ramp generators
        generators = ChannelList(self,
                                      "Generators",
                                      RampGenerator,
                                      snapshotable = False,
                                      multichan_paramclass = None
                                      )
        
        ramp_gens = ('a', 'b', 'c', 'd')

        for i in range(0,4):
            generator = RampGenerator(self, 'ramp{:1}'.format(ramp_gens[i]), ramp_gens[i])
            generators.append(generator)
            self.add_submodule('ramp{:1}'.format(ramp_gens[i]), generator)
        generators.lock()
        self.add_submodule('ramp_generators', generators)


        #create AWG generators
        arbitrary_generators = ChannelList(self,
                                      "Arbitrary_Generators",
                                      AWG,
                                      snapshotable = False,
                                      multichan_paramclass = None
                                      )
        
        aw_gens = ('a', 'b', 'c', 'd')

        for i in range (0, int(num_chans/6)):
            arbitrary_generator = AWG(self, 'awg{:1}'.format(aw_gens[i]), aw_gens[i])
            arbitrary_generators.append(arbitrary_generator)
            self.add_submodule('awg{:1}'.format(aw_gens[i]), arbitrary_generator)
        arbitrary_generators.lock()
        self.add_submodule('aw_generators', arbitrary_generators)






        """
        Below this is our poor swiss coder's work 
        """


        # # switch all channels ON if still OFF
        # if 'OFF' in self.query_all():
        #     self.all_on()
            
        self.connect_message()
        print('Current DAC output: ' +  str(self.channels[:].volt.get()))

    def _set_voltage(self, chan, code):
        return self.write('{:0} {:X}'.format(chan, code))
            
    def _read_voltage(self, chan):
        dac_code=self.write('{:0} V?'.format(chan))
        return self._dacval_to_vval(dac_code)

    def set_all(self, volt):
        """
        Set all dac channels to a specific voltage.
        """
        for chan in self.channels:
            chan.volt.set(volt)
    
    def query_all(self):
        """
        Query status of all DAC channels
        """
        reply = self.write('All S?')
        print(reply)
        return reply.replace("\r\n","").split(';')
    
    def all_on(self):
        """
        Turn on all channels.
        """
        return self.write('ALL ON')
      
    def all_off(self):
        """
        Turn off all channels.
        """
        return self.write('ALL OFF')
    
    def empty_buffer(self):
        # make sure every reply was read from the DAC 
       # while self.visa_handle.bytes_in_buffer:
       #     print(self.visa_handle.bytes_in_buffer)
       #     print("Unread bytes in the buffer of DAC SP1060 have been found. Reading the buffer ...")
       #     print(self.visa_handle.read_raw())
       #      self.visa_handle.read_raw()
       #     print("... done")
        self.visa_handle.clear() 
          
    def write(self, cmd):
        """
        Since there is always a return code from the instrument, we use ask instead of write
        TODO: interpret the return code (0: no error)
        """
        # make sure there is nothing in the buffer
        self.empty_buffer()  
        
        return self.ask(cmd)
    
    def get_serial(self):
        """
        Returns the serial number of the device
        Note that when querying "HARD?" multiple statements, each terminated
        by \r\n are returned, i.e. the device`s reply is not terminated with 
        the first \n received
        """
        self.write('HARD?')
        reply = self.visa_handle.read()
        time.sleep(0.01)
       # while self.visa_handle.bytes_in_buffer:
       #     self.visa_handle.read_raw()
       #     time.sleep(0.01)
        self.empty_buffer()
        return reply.strip()[3:]
    
    def get_firmware(self):
        """
        Returns the firmware of the device
        Note that when querying "HARD?" multiple statements, each terminated
        by \r\n are returned, i.e. the device`s reply is not terminated with 
        the first \n received
        """
        self.write('SOFT?')
        reply = self.visa_handle.read()
        time.sleep(0.01)
       # while self.visa_handle.bytes_in_buffer:
       #     self.visa_handle.read_raw()
       #     time.sleep(0.01)
        self.empty_buffer()
        return reply.strip()[-5:]
        
    
    def get_idn(self):
        SN = self.get_serial()
        FW = self.get_firmware()
        return dict(zip(('vendor', 'model', 'serial', 'firmware'), 
                        ('BasPI', 'LNHR DAC SP1060', SN, FW)))
                        

#reference this
    def set_newWaveform(self, channel = '12', waveform = '0', frequency = '100.0', 
                        amplitude = '5.0', wavemem = '0'):
        """
        Write the Standard Waveform Function to be generated
        - Channel: [1 ... 24]
        Note: AWG-A and AWG-B only DAC-Channel[1...12], AWG-C and AWG-D only DAC-Channel[13...24]
        - Waveforms: 
            0 = Sine function, for a Cosine function select a Phase [°] of 90°
            1 = Triangle function
            2 = Sawtooth function
            3 = Ramp function
            4 = Pulse function, the parameter Duty-Cycle is applied
            5 = Gaussian Noise (Fixed), always the same seed for the random/noise-generator
            6 = Gaussian Noise (Random), random seed for the random/noise-generator
            7 = DC-Voltage only, a fixed voltage is generated
        - Frequency: AWG-Frequency [0.001 ... 10.000]
        - Amplitude: [-50.000000 ... 50.000000]
        - Wave-Memory (WAV-A/B/C/D) are represented by 0/1/2/3 respectively
        """
        memsave = ''
        if (wavemem == '0'):
            memsave = 'A'
        elif (wavemem == '1'):
            memsave = 'B'
        elif (wavemem == '2'):
            memsave = 'C'
        elif (wavemem == '3'):
            memsave = 'D'

        sleep_time = 0.02

        self.write('C WAV-B CLR') # Wave-Memory Clear.
        time.sleep(sleep_time)
        self.write('C SWG MODE 0') # generate new Waveform.
        time.sleep(sleep_time)
        self.write('C SWG WF ' + waveform) # set the waveform.
        time.sleep(sleep_time)
        self.write('C SWG DF ' + frequency) # set frequency.
        time.sleep(sleep_time)
        self.write('C SWG AMP ' + amplitude) # set the amplitude.
        time.sleep(sleep_time)
        self.write('C SWG WMEM ' + wavemem) # set the Wave-Memory.
        time.sleep(sleep_time)
        self.write('C SWG WFUN 0') # COPY to Wave-MEM -> Overwrite.
        time.sleep(sleep_time)
        self.write('C SWG LIN ' + channel) # COPY to Wave-MEM -> Overwrite.
        time.sleep(sleep_time)
        self.write('C AWG-' + memsave + ' CH ' + channel) # Write the Selected DAC-Channel for the AWG.
        time.sleep(sleep_time)
        self.write('C SWG APPLY') # Apply Wave-Function to Wave-Memory Now.
        time.sleep(sleep_time)
        self.write('C WAV-' + memsave + ' SAVE') # Save the selected Wave-Memory (WAV-A/B/C/D) to the internal volatile memory.
        time.sleep(sleep_time)
        self.write('C WAV-' + memsave + ' WRITE') # Write the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory (AWG-A/B/C/D).
        time.sleep(0.5)
        self.write('C AWG-' + memsave + ' START') # Apply Wave-Function to Wave-Memory Now.

    def set_bandwidth(self, chan, code):
            return self.write('{:0} {:1}'.format(chan, code))

    def get_bandwidth(self, chan):
            dac_code = self.write('{:0} BW?'.format(chan))
            return dac_code
        
    def read_mode(self, chan):
            dac_code = self.write('{:0} M?'.format(chan))
            return dac_code



############################################################

#                     SET COMMANDS

############################################################
###  SET commands can be repeated at a maximum of 1KHz (1 msec)

### SET DAC commands always return a numeric response from the device:
    """
    "0" = No error (normal)
    "1" = Invalid DAC-Channel
    "2" = Missing DAC-Value, Status or BW
    "3" = DAC-Value out of range
    "4" = Mistyped
    "5" = Writing not allowed (Ramp/Step-Generator or AWG are running on this DAC-
    Channel)
    """


    """
    Set a specific DAC channel to a specified voltage.
    @chan - integer indicating channel
    @voltage - hexadecimal voltage value
    """
    def set_chan_voltage(self, chan, voltage):
        code = self.write('{:0} {:X}'.format(chan, voltage))
        return self.handleDACSetErrors(code) 

    """
    Set all dac channels to a specific voltage.
    @voltage - hexadecimal voltage value
    """
    def set_all_voltage(self, voltage):
        code = self.write('ALL {:X}'.format(voltage))
        return self.handleDACSetErrors(code) 
    
    """
    turn on the specified channel
    @chan - integer 
    """
    def set_chan_on(self, chan):
        code = self.write('{0} ON'.format(chan))
        return self.handleDACSetErrors(code) 

    """
    turn off the specified channel
    @chan - integer 
    """
    def set_chan_off(self, chan):
        code = self.write('{0} OFF'.format(chan))
        return self.handleDACSetErrors(code) 

    """
    Turn on all channels.
    """
    def set_all_on(self):
        code = self.write('ALL ON')
        return self.handleDACSetErrors(code) 
      
      
    """
    Turn off all channels.
    """
    def set_all_off(self):
        code = self.write('ALL OFF')
        return self.handleDACSetErrors(code) 

    """
    Set the bandwidth of a specified channel (High or Low)
    @chan - integer 
    @code - string ("HBW"/"LBW")
    """
    def set_chan_bandwidth(self, chan, code):
        code = self.write('{} {}'.format(chan, code))
        return self.handleDACSetErrors(code) 
    """
    Set the bandwidth of all channels (High or Low)
    @code - string ("HBW"/"LBW")
    """
    def set_all_bandwidth(self, code):
        code = self.write('ALL {}'.format(code))
        return self.handleDACSetErrors(code) 

#### All AWG SET Commands return a numeric response:
    """
    "0" = No error (normal)
    "1" = Invalid AWG-Memory
    "2" = Missing AWG-Address and/or AWG-Value
    "3" = AWG-Address and/or AWG-Value out of range
    "4" = Mistyped
    """
####

    """
    Set an AWG_memory address to a value
    @mem - character specifiying AWG-memory
    @adr - hexadecimal address
    @value - hexadecimal value of voltage
    """
    def set_adr_AWGmem(self, mem, adr, value):
        code = self.write("AWG-{} {:X} {:X}".format(mem, adr, value))

    def set_all_AWGMem(self, mem, value):
        code = self.write("AWG-{} ALL {:X}".format(mem, value))

#### All WAV SET Commands return a numeric response:
    """
    "0" = No error (normal)
    "1" = Invalid WAV-Memory
    "2" = Missing WAV-Address and/or WAV-Voltage
    "3" = WAV-Address and/or WAV-Voltage out of range
    "4" = Mistyped
    """
####

    """
    Set a WAV-memory address to a value
    @mem - character specifiying WAV-memory
    @adr - hecadecimal address
    @value - hexadecimal value of voltage
    """
    def set_adr_WAVMem(self, mem, adr, value):
        code = self.write("WAV-{0} {:X} {:X}".format(mem, adr, value))

    def set_all_WAVMem(self, mem, value):
        code = self.write("WAV-{0} ALL {:X}".format(mem, value))

#### POLY command return codes:
    """
    "0" = No error (normal)
    "1" = Invalid Polynomial Name
    "2" = Missing Polynomial Coefficient(s)
    "4" = Mistyped
    """
####

    """
    Set polynomial coefficients
    @mem - character of a polynomial memory
    @coefs - list of floating point values representing the coefficients (a0, a1, a2, a3...)
    
    """
    def set_polynomial(self, mem, coefs):
        fs = [str(c) for c in coefs]
        code = self.write('POLY-{} {}'.format(mem, ' '.join(fs)))


############################################################

#                    QUERY DATA COMMANDS

############################################################

    """
    Read the actual voltage of a specified channel
    @chan - integer 
    """
    def query_chan_voltage(self, chan):
        dac_code=self.write('{:0} V?'.format(chan))
        return self._dacval_to_vval(dac_code)

    def query_all_voltage(self):
        dac_code=self.write('ALL V?')
        return dac_code

    """
    Read the registered voltage of a specified channel
    @chan - integer 
    """
    def query_chan_voltageReg(self, chan):
        dac_code=self.write('{:0} VR?'.format(chan))
        return self._dacval_to_vval(dac_code)

    def query_all_voltageReg(self):
        dac_code=self.write('ALL VR?')
        return dac_code


    """
    Query status of a channel
    @chan - integer 
    """
    def query_chan_status(self, chan):
        reply = self.write('{0} S?'.format(chan))
        return reply

    """
    Query status of all DAC channels
    """
    def query_all_status(self):
        reply = self.write('All S?')
        return reply.replace("\r\n","").split(';')
    
    """
    Query a bandwidth of a channel
    @chan - integer specifying channel
    """
    def query_chan_bandwidth(self, chan):
        reply = self.write('{0} BW?'.format(chan))
        return reply

    def query_all_bandwidth(self):
        reply = self.write('ALL BW?')
        return reply.replace("\r\n","").split(';')

    """
    Query a DAC mode
    MODES are ERR/DAC/SYN/RMP/AWG/---
    See section 7.1.10 of programming manual for descriptions
    @chan - integer specifying channel
    """
    def query_chan_DACMode(self, chan):
        reply = self.write('{0} M?'.format(chan))
        return reply
    
    def query_all_DACMode(self):
        reply = self.write('ALL M?')
        return reply.replace("\r\n","").split(';')

    """
    Query memory contents of AWG memory at address(es)
    @mem - character indicating AWG memory A/B/C/D
    @adr - hex number indicating address
    """
    def query_adr_AWGmem(self, mem, adr):
        reply = self.write('AWG-{0} {:X}?'.format(mem, adr))
        return reply

    """
    Queries a block of 1,000 AWG hex values starting at block_start
    @mem - character indicating AWG memory A/B/C/D
    @block_start - hex number indicating start address
    """
    def query_block_AWGmem(self, mem, block_start):
        reply = self.write('AWG-{0} {:X} BLK?'.format(mem, block_start))
        return reply.replace("\r\n","").split(';')

    """
    Queries memory contents of WAV memory at address(es)
    @mem - character indicating AWG memory A/B/C/D
    @adr - hex number indicating address
    """
    def query_adr_WAVmem(self, mem, adr):
        reply = self.write('WAV-{0} {:X}?'.format(mem, adr))
        return reply

    """
    Queries a block of 1,000 WAV hex values starting at block_start
    @mem - character indicating AWG memory A/B/C/D
    @block_start - hex number indicating start address
    """
    def query_block_WAVmem(self, mem, block_start):
        reply = self.write('WAV-{0} {:X} BLK?'.format(mem, block_start))
        return reply.replace("\r\n","").split(';')

    """
    Query polynomial coefficients of a poly mem
    @mem - character indicating poly memory A/B/C/D
    """
    def query_coefs_Polymem(self, mem):
        reply = self.write('POLY-{0}?'.format(mem))
        return reply.replace("\r\n","").split(';')

             
############################################################

#                    QUERY INFORMATION COMMANDS

############################################################
    def get_serial(self):
        """
        Returns the serial number of the device
        Note that when querying "HARD?" multiple statements, each terminated
        by \r\n are returned, i.e. the device`s reply is not terminated with 
        the first \n received
        """
        self.write('HARD?')
        reply = self.visa_handle.read()
        time.sleep(0.01)
       # while self.visa_handle.bytes_in_buffer:
       #     self.visa_handle.read_raw()
       #     time.sleep(0.01)
        self.empty_buffer()
        return reply.strip()[3:]

    """
    Returns overview of the ASCII commands and queries
    """
    def get_overview(self):
        reply = self.write('?')
        return reply

    """
    Shows the help text
    """
    def get_help(self):
        reply = self.write("HELP?")
        return reply

    """
    Shows the health of the device (temperature, cpu-load, power-supplies)
    """
    def get_health(self):
        reply = self.write("HEALTH?")
        return reply

    """
    Obtains the IP address of the DAC
    """
    def get_ip(self):
        reply = self.write("IP?")
        return reply

    """
    Provides contact information (name, lab, website, email. phone)
    """
    def get_contact(self):
        reply = self.write("CONTACT?")
        return reply

    
    def get_firmware(self):
        """
        Returns the firmware of the device
        Note that when querying "HARD?" multiple statements, each terminated
        by \r\n are returned, i.e. the device`s reply is not terminated with 
        the first \n received
        """
        self.write('SOFT?')
        reply = self.visa_handle.read()
        time.sleep(0.01)
       # while self.visa_handle.bytes_in_buffer:
       #     self.visa_handle.read_raw()
       #     time.sleep(0.01)
        self.empty_buffer()
        return reply.strip()[-5:]
        
    """
    Obtain identification numbers and other manufacturer information about the DAC
    """
    def get_idn(self):
        SN = self.get_serial()
        FW = self.get_firmware()
        return dict(zip(('vendor', 'model', 'serial', 'firmware'), 
                        ('BasPI', 'LNHR DAC SP1060', SN, FW)))
                        

######################################################################################

#                  DAC Update-Mode and Synchronization CONTROL COMMANDS

######################################################################################
    """
    Returns the update mode of the device for the given board (higher or lower)
    @board - character, 'H'/'L' for higher or lower board
    """
    def read_updateMode(self, board):
        return self.write("C UM-{}?".format(board))

    """
    Writes the update mode for the higher or lower board.
    @board - character, 'H'/'L' for higher or lower board
    @mode = integer, either 0/1 for instantly/synchronous
    """
    def write_updateMode(self, board, mode):
        self.write("C UM-{} {}".format(board, mode))


    """
    Makes a synchronous DAC-update of all 12 channels on one DAC Board,
    or on both in parallel
    @board - string indicating board(s) to update: "H"/"L"/"HL" for higher/lower/both
    """
    def update_board_sync(self, board):
        return self.write("C SYNC-{}".format(board))

######################################################################################

#                  RAMP/STEP-Generator CONTROL COMMANDS

######################################################################################

    """
    Control the mode of the four RAMP/STEP generators.
    Modes are START, STOP, HOLD.  Ramp memories are A/B/C/D.
    By indicating "ALL" you can control all 4 generators.
    @mem - the ramp memory to control: A/B/C/D/ALL
    @mode - string indicating mode: HOLD/START/STOP
    """
    def write_rampMode(self, mem, mode):
        return self.write("C RMP-{} {}".format(mem, mode))

    """
    Read the state of one ramp generator
    States are Idle/Ramp_UP/Ramp_DOWN/Hold (coded as 0/1/2/3, respectively)
    @mem - character indicating ramp mem: A/B/C/D
    """
    def read_rampState(self, mem):
        return self.write("C RMP-{} S?".format(mem))

    """
    Read the cycles done since the start of the specified ramp generator
    @mem - character indicating ramp mem: A/B/C/D 
    """
    def read_rampCyclesDone(self, mem):
        return self.write("C RMP-{} CD?".format(mem))

    """
    Read the steps done since the start of the specified ramp generator
    @mem - character indicating ramp mem: A/B/C/D 
    """
    def read_rampStepsDone(self, mem):
        return self.write("C RMP-{} SD?".format(mem))

    """
    Reads the step-size voltage of the specified ramp generator
    @mem - character indicating ramp mem: A/B/C/D 
    """
    def read_rampStepSizeVoltage(self, mem):
        return self.write("C RMP-{} SSV?".format(mem))

    """
    Read the calculated step per cycle of a ramp memory.
    @mem - character indicating ramp mem: A/B/C/D
    """
    def read_rampStepsPerCycle(self, mem):
        return self.write("C RMP-{} ST?".format(mem))

    """
    Readout if the selected DAC-Channel of the RAMP/STEP-Generator (RMP-A/B/C/D) is
    available (not used by other RAMP- or AWG-Channels). The returned integer number
    gives the availability:
        0=Not Available/1=Available
    A running generator always reads not available.
    @mem - character indicating ramp mem: A/B/C/D
    """
    def read_rampChannelAvailable(self, mem):
        return self.write("C RMP-{} AVA?".format(mem))

    """
    Read or write the Selected DAC-Channel for the RAMP/STEP-Generator (RMP-A/B/C/D).
    The DAC-Channel can be in the range from 1 to 24. After writing the Selected DAC-
    Channel, its availability can be checked
    @mem - character indicating ramp mem: A/B/C/D 
    @chan - integer specifying the channel
    """
    def read_rampSelectedChannel(self, mem):
        return self.write("C RMP-{} CH?".format(mem))

    def write_rampSelectedChannel(self, mem, chan):
        return self.write("C RMP-{} CH {}".format(mem, chan))
    """
    Read or write the Start Voltages of the RAMP/STEP-Generators (RMP-A/B/C/D). The
    Start Voltage is a floating-point number in the range between -10.000000 V and
    +10.000000 V; the decimal point must be a period (point).
    @mem - character indicating ramp mem: A/B/C/D 
    @voltage - floating point number indicating voltage
    """
    def read_rampStartVoltage(self, mem):
        return self.write("C RMP-{} STAV?".format(mem))

    def write_rampStartVoltage(self, mem, voltage):
        return self.write("C RMP-{} STAV {}".format(mem, voltage))
    """
    Read or write the Stop/Peak Voltages of the RAMP/STEP-Generators (RMP-A/B/C/D).
    The Stop/Peak Voltage is a floating-point number in the range between -10.000000 V and
    +10.000000 V; the decimal point must be a period (point). If the RAMP Shape is UP-ONLY
    (Sawtooth function) this value is the Stop Voltage. If the RAMP Shape is UP and DOWN
    (Triangle function) this value is the Peak Voltage, since the Triangle function returns to
    the Start Voltage.
    @mem - character indicating ramp mem: A/B/C/D 
    @voltage - floating point number indicating voltage
    """
    def read_rampStopPeakVoltage(self, mem):
        return self.write("C RMP-{} STOV?".format(mem))

    def write_rampStopPeakVoltage(self, mem, voltage):
        return self.write("C RMP-{} STOV {}".format(mem, voltage))
    """
    Read or write the RAMP Times of the RAMP/STEP-Generators (RMP-A/B/C/D). The
    RAMP Time is a floating-point number in the range between 0.05 second and 1E6 seconds
    (equal to 277.7 hours); the decimal point must be a period (point). The inherent
    resolution is given by the RAMP/STEP-Generator cycle of 5 msec (0.005 second).
    @mem - character indicating ramp mem: A/B/C/D 
    @time - floating point number of seconds
    """
    def read_rampTime(self, mem):
        return self.write("C RMP-{} RT?".format(mem))

    def write_rampTime(self, mem, time):
        return self.write("C RMP-{} RT {}".format(mem, time))
    """
    Read or write the RAMP Shape of the RAMP/STEP-Generators (RMP-A/B/C/D). Two
    different Shapes of the Ramping/Stepping function can be written or readout:
    0=UP-ONLY (Sawtooth function)/1=UP and DOWN (Triangle function)
    @mem - character indicating ramp mem: A/B/C/D 
    @shape - integer 0/1 indicating shape of RAMP function
    """
    def read_rampShape(self, mem):
        return self.write("C RMP-{} RS?".format(mem))

    def write_rampShape(self, mem, shape):
        return self.write("C RMP-{} RS {}".format(mem, shape))
    """
    Read or write the number of RAMP Cycles-Set (0....4E9) of the four RAMP/STEP-
    Generators (RMP-A/B/C/D). The integer number represents the number of RAMP Cycles-
    Set until the RAMP/STEP-Generator gets stopped. If the number of RAMP Cycles-Set is
    zero (0), an infinite number of RAMP Cycles are done; the RAMP/STEP-Generator runs
    until it is stopped by the user
    @mem - character indicating ramp mem: A/B/C/D 
    @cycles - integer specifying cycles 
    """
    def read_rampCyclesSet(self, mem):
        return self.write("C RMP-{} CS?".format(mem))

    def write_rampCyclesSet(self, mem, cycles):
        return self.write("C RMP-{} CS {}".format(mem, cycles))

    """
    Read or write the RAMP/STEP-Selection of the four RAMP/STEP-Generators (RMP-
    A/B/C/D). The RAMP/STEP-Generators can be switched between RAMP function and
    STEP function. The normal RAMP function periodically updates the DAC-Voltage each
    5 msec. The STEP function updates the DAC-Voltage when the AWG has stopped (single
    cycle); this used for 2D-Scans. The two different functions (RAMP/STEP) can be written
    or readout:
    0=RAMP function/1=STEP function
    @mem - character indicating ramp mem: A/B/C/D 
    @sel - integer indicating selection, 0: RAMP, 1: STEP
    """
    def read_rampStepSelection(self, mem):
        return self.write("C RMP-{} STEP?".format(mem))

    def write_rampStepSelection(self, mem, sel):
        return self.write("C RMP-{} STEP {}".format(mem, sel))



######################################################################################

#                  2D-Scan CONTROL COMMANDS

######################################################################################
    """
    Read or write the Boolean parameter Normal-Start / Auto-Start AWG. If Auto-Start AWG
    is selected (1) the AWG gets automatically restarted after the STEP-Generator has been
    updated. A minimum time delay of 5 msec is implemented from the update of the STEP-
    Generator to the restart of the AWG.
    If Auto-Start AWG is deselected (0) the AWG starts normally by an external TTL-Trigger
    or via a CONTROL Command. The two different modes (Normal-Start AWG or Auto-Start
    AWG) can be written or readout:
    0=Normal-Start AWG/1=Auto-Start AWG
    @mem - character indicating AWG memory A/B/C/D
    @mode - integer of start mode, 0: normal 1: auto
    """
    def read_AWGStartMode(self, mem):
        return self.write("C AWG-{} AS?".format(mem, mode))

    def write_AWGStartMode(self, mem, mode):
        return self.write("C AWG-{} AS {}".format(mem, mode))

    """
    Read or write the Boolean parameter Keep/Reload AWG MEM. If Reload AWG MEM is
    selected (1) the AWG-Memory (AWG-A/B/C/D) is reloaded from the corresponding
    Wave-Memory (WAV-A/B/C/D) before it gets restarted. This is option is slower, but has
    to be selected since the Polynomial (POLY-A/B/C/D) must be applied to perform an
    adaptive 2D-Scan
    If Keep AWG MEM is selected (0) the predefined AWG-Memory is used for a next scan-
    line, which allows a faster 2D-Scan, but without adaption. These two different behaviors
    (Keep AWG MEM or Reload AWG MEM) can be written or readout:
    0=Keep AWG MEM/1=Reload AWG MEM
    @mem - character indicating AWG memory A/B/C/D
    @mode - integer of mode, 0/1 (keep/reload)
    """
    def read_AWGReloadMode(self, mem):
        return self.write("C AWG-{} RLD?".format(mem, mode))

    def write_AWGReloadMode(self, mem, mode):
        return self.write("C AWG-{} RLD {}".format(mem, mode))
    """
    Read or write the Boolean parameter Skip/Apply Polynomial. If Apply Polynomial is
    selected (1) the Polynomial (POLY-A/B/C/D) is applied when the AWG-Memory (AWG-
    A/B/C/D) is reloaded from the corresponding Wave-Memory (WAV-A/B/C/D); this is
    essential for an adaptive 2D-Scan. The Polynomial (POLY-A/B/C/D) can be updated fast
    by using the SET POLY Command or by using the parameter “Adaptive Shift-Voltage” – see
    description below.
    If Skip Polynomial is selected the Polynomial (POLY-A/B/C/D) isn’t applied when the
    predefined Wave-Memory (WAV-A/B/C/D) is written to the AWG-Memory (AWG-
    A/B/C/D). These two different behaviors (Skip Polynomial or Apply Polynomial) can be
    written or readout:
    0=Skip Polynomial/1=Apply Polynomial
    @mam - character of poly memory A/B/C/D
    @mode - ingeger indicating mode 0/1 (skip/apply)
    """
    def read_AWGApplyPolyMode(self, mem):
        return self.write("C AWG-{} AP?".format(mem, mode))

    def write_AWGApplyPolyMode(self, mem, mode):
        return self.write("C AWG-{} AP {}".format(mem, mode))
    """
    Read or write the Adaptive Shift-Voltage per Step of the STEP-Generators (RMP-
    A/B/C/D). A simple adaptive 2D-Scan (with linear y-adaption) can be performed by this
    parameter. This Shift-Voltage gets applied to the AWG function (y-Axis) after each step of
    the STEP-Generator (x-Axis). This is automatically done by linearly modifying the
    polynomial coefficient a 0 (constant) after each step. This coefficient a 0 is calculated by
    multiplying the Adaptive Shift-Voltage by the RAMP Cycles-Done. If the Adaptive Shift-
    Voltage is zero (0) the polynomial will not be changed.
    Since it is allowed to modify this Adaptive Shift-Voltage while a 2D-Scan is running, also
    nonlinear adaptions can be easily implemented.
    The Adaptive Shift-Voltage is a floating-point number in the range between -10.000000 V
    and +10.000000 V per Step; the decimal point must be a period (point).
    @mem - character indicating AWG memory A/B/C/D
    @voltage - floating point number of voltage
    """
    def read_AWGShiftVoltage(self, mem):
        return self.write("C AWG-{} SHIV?".format(mem, mode))

    def write_AWGShiftVoltage(self, mem, voltage):
        return self.write("C AWG-{} SHIV {}".format(mem, voltage))


######################################################################################

#                  AWG CONTROL COMMANDS 

######################################################################################
    """
    Read or write the Boolean parameter AWG Normal/AWG Only, related to the Lower DAC
    Board (AWG-A/B) or to the Higher DAC-Board (AWG-C/D). If AWG Only is selected (1), all
    the other DAC-CHANNELs on this DAC-Board get blocked (---) and only the AWG-Channels
    are active; this results in lower time-jitter for these AWG-Channels.
    If AWG Normal is selected (0) the other DAC-CHANNELs on the corresponding DAC-Board
    are free to be used for normal DAC operation (DAC) or as RAMP/STEP-Generator (RMP).
    These two different options (AWG Normal or AWG Only) can be written or readout:
    0=AWG Normal/1=AWG Only
    @board - string indicating board, AB/CD for lower/higher board
    @mode - integer of mode, 0/1 (awg normal, awg only)
    """
    def read_AWGNormalMode(self, board):
        return self.write("C AWG-{} ONLY?".format(board))

    def write_AWGNormalMode(self, board, mode): 
        return self.write("C AWG-{} ONLY {}".format(board, mode))
    """
    Control the mode of the four AWGs (AWG-A/B/C/D) by the two Boolean controls Start
    and Stop. After setting theses controls, they are reset internally. AWG-AB allows
    synchronous access to the two AWGs on the Lower DAC-Board and AWG-CD to the two
    AWGs on the Higher DAC-Board. AWG-ALL makes synchronous access to all the four
    AWGs. A synchronous start of multiple AWGs (AB/CD/ALL) can only be performed when
    all these AWGs are in Idle-Mode.
    @mem - character indicating the AWG memory or memories A/B/C/D/AB/CD/ALL
    @mode - string indicating control mode, START/STOP
    """
    def write_AWGControlMode(self, mem, mode): 
        return self.write("C AWG-{} {}".format(mem, mode))
    """
    Readout the State (Idle/Running) of the four AWGs (AWG-A/B/C/D). The returned
    integer number defines the actual state:
    0=Idle/1=Running
    @mem - character indicating AWG memory A/B/C/D
    """
    def read_AWGState(self, mem):
        return self.write("C AWG-{} S?".format(mem))

    """
    Readout the AWG Cycles-Done of the four AWGs (AWG-A/B/C/D). The returned integer
    number represents the completed AWG Cycles since the Start; it is in a range from 0 to
    4E9. When the AWG is stopped (state Idle) the AWG Cycles-Done shows the last value;
    when the AWG is started it is reset to zero (0). After power-up all the AWG Cycles-Done
    counters are zero (0)
    @mem - character indicating AWG memory A/B/C/D
    """
    def read_AWGCyclesDone(self, mem): 
        return self.write("C AWG-{} CD?".format(mem))
    """
    Readout the Duration/Period of a complete AWG-Cycle (AWG Memory_Size * AWG Clock-
    Period) of the four AWGs (AWG-A/B/C/D). The unit of the Duration/Period is second
    (sec). The minimum AWG Memory Size is 2 and the minimum AWG Clock-Period is 10E-
    6 sec, resulting in a minimum Duration/Period is 20E-6 sec. The maximum
    Duration/Period of 1.36E8 sec is given by the maximum AWG Memory Size of 34’000 and
    the maximum AWG Clock-Period 4’000 sec (4E9 * 1E-6 sec).
    The Duration/Period is a floating-point/exponential (E) number with a period (point) as
    decimal separator
    @mem - character indicating AWG memory A/B/C/D
    """
    def read_AWGDuration(self, mem):
        return self.write("C AWG-{} DP?".format(mem))
    """
    Readout if the selected DAC-Channel of the AWG (AWG-A/B/C/D) is available (not used
    by other AWG- or RAMP-Channels). The returned integer number gives the availability:
    0=Not Available/1=Available
    Note: A running AWG reads always “Not Available (0)” on its DAC-Channel.
    @mem - character indicating AWG memory A/B/C/D
    """
    def read_AWGChannelAvailable(self, mem): 
        return self.write("C AWG-{} AVA?".format(mem))
    """
    Read or write the Selected DAC-Channel for the AWG (AWG-A/B/C/D). Since the AWG-A
    and the AWG-B are running on the Lower DAC-Board, their DAC-Channels can only be in
    the range from 1 to 12. The AWG-C and the AWG-D are running on the Higher DAC-Board
    and therefor the DAC-Channels are restricted to the range from 13 to 24.
    After writing the Selected DAC-Channel, its availability can be checked
    @mem - character indicating AWG memory A/B/C/D
    @chan - integer of channel
    """
    def read_AWGSelectedChannel(self, mem):
        return self.write("C AWG-{} CH?".format(mem))
    
    def write_AWGSelectedChannel(self, mem, chan): 
        return self.write("C AWG-{} CH {}".format(mem, chan))
    """
    Read or write the AWG-Memory Size of the AWG (AWG-A/B/C/D) which is an integer
    number in the range from 2 to 34’000. Each point of the AWG-Memory corresponds to a
    24-bit DAC-Value.
    The AWG streams this AWG-Memory Size number to the DAC when the AWG is started.
    This is independent of the number of programmed AWG-Memory Addresses. If the user
    has downloaded an AWG-Waveform consisting of 1’000 points, also the AWG-Memory
    Size has to be set to 1’000.
    @mem - character indicating AWG memory A/B/C/D
    @size - integer of memory size
    """
    def read_AWGMemorySize(self, mem):
        return self.write("C AWG-{} MS?".format(mem))

    def write_AWGMemorySize(self, mem, size): 
        return self.write("C AWG-{} MS {}".format(mem, size))
    """
    Read or write the number of AWG Cycles-Set (0....4E9) of one of the four AWGs (AWG-
    A/B/C/D). The integer number represents the number of AWG Cycles-Set until the AWG
    gets stopped. If the number of AWG Cycles-Set is zero (0), an infinite number of AWG-
    Cycles are done; the AWG runs until it is stopped by the user.
    @mem - character indicating AWG memory A/B/C/D
    @cycles - integer of number of cycles
    """
    def read_AWGCyclesSet(self, mem):
        return self.write("C AWG-{} CS?".format(mem))

    def write_AWGCyclesSet(self, mem, cycles): 
        return self.write("C AWG-{} CS {}".format(mem, cycles))
    """
    Read or write the External Trigger Mode of one of the four AWGs (AWG-A/B/C/D). This
    sets the behavior of the four digital inputs “Trig In AWG-A/B/C/D” on the back panel of
    the device. The external applied TTL trigger-signals can be programmed to have the
    following four different functionalities:
    - Disabled (0): The trigger-input has no impact.
    - START only (1): The AWG starts on a rising edge of the TTL-signal.
    - START-STOP (2): The AWG starts on a rising edge and stops on a falling edge.
    - SINGLE-STEP (3): The AWG starts on a rising edge of the TTL-signal and the AWG makes
    a single step for each rising edge. Therefore, the AWG Clock is defined by the external
    applied TTL trigger-signal from DC up to maximum 100 kHz (PW minimum 2 μsec).
    @mem - character indicating AWG memory A/B/C/D
    @mode - integer indicating mode 0/1/2/3 (disabled/START only/START-STOP/SINGLE STEP)
    """
    def read_AWGExtTriggerMode(self, mem):
        return self.write("C AWG-{} TM?".format(mem))

    def write_AWGExtTriggerMode(self, mem, mode): 
        return self.write("C AWG-{} TM {}".format(mem, mode))
    """
    Read or write the Clock-Period [μsec] (10....4E9) of the Lower (AWG-A+B) or the Higher
    DAC-Board (AWG-C+D). This integer number represents the AWG Clock-Period in μsec
    (1E-6 sec) and the minimum is 10 μsec and the maximum 4E9 μsec which corresponds to
    4’000 sec (4E9 * 1E-6 sec). The resolution of the Clock-Period is 1 μsec.
    The Lower AWG Clock-Period [μsec] is common for the AWG-A and the AWG-B, running
    on the Lower DAC-Board. The Higher AWG Clock-Period [μsec] is common for the AWG-C
    and the AWG-D, running on the Higher DAC-Board.
    @board - string indicating AWG board, AB/CD (lower, higher)
    @T - integer specifying period
    """
    def read_AWGClkPeriod(self, board):
        return self.write("C AWG-{} CP?".format(board))

    def write_AWGClkPeriod(self, board, T): 
        return self.write("C AWG-{} CP {}".format(board, T))
    """
    Read or write the Control-Status (ON/OFF) of the external digital AWG 1 MHz Clock
    Reference TTL signal (on the D-SUB connector on the back-panel). This 1 MHz reference
    clock is internally used for the AWGs and it can be used to synchronize other devices with
    the LNHR DAC II
    @mode - integer of mode 0/1 (OFF/ON)
    """
    def read_AWGClkRefState(self):
        return self.write("C AWG-1MHz?")

    def write_AWGClkRefState(self, mode): 
        return self.write("C AWG-1MHz {}".format(mode))


######################################################################################

#                  STANDARD WAVEFORM GENERATION (SWG) CONTROL COMMANDS

######################################################################################
    """
    Read or write the Boolean parameter SWG Mode which can be either “Generate New
    Waveform” (0) or “Use Saved Waveform” (1). When the default Mode “Generate New
    Waveform” is selected, a new waveform can be generated by using the Standard
    Waveforms and the Wave-Functions. In the “Use Saved Waveform” Mode the previously
    saved waveform (WAV-S) is recalled and the selected Wave-Functions can be applied on
    this recalled waveform; e.g., it can be copied to a Wave-Memory (WAV-A/B/C/D).
    @mode - integer of SWG mode 0/1 (use saved waveform/generate new waveform)
    """
    def read_SWGMode(self):
        return self.write("C SWG MODE?")

    def write_SWGMode(self, mode):
        return self.write("C SWG MODE {}".format(mode))
    """
    Read or write the Standard Waveform Function to be generated. The following eight
    different functions can be selected and are represented by these integer numbers:
    0 = Sine function – for a Cosine function select a Phase [°] of 90°
    1 = Triangle function
    2 = Sawtooth function
    3 = Ramp function
    4 = Pulse function – the parameter Duty-Cycle [%] is applied
    5 = Gaussian Noise (Fixed) – always the same seed for the random/noise-generator
    6 = Gaussian Noise (Random) – random seed for the random/noise-generator
    7 = DC-Voltage only – a fixed voltage is generated
    @func - integer specifying function to be written, 0/1/2/3/4/5/6/7 (see above for coding scheme)
    """
    def read_SWGFunction(self):
        return self.write("C SWG WF?")

    def write_SWGFunction(self, func):
        return self.write("C SWG WF {}".format(func))
    """
    Read or write the Desired AWG-Frequency [Hz] of the Wave- and AWG-function.
    Sometimes it isn’t possible to reach exact this frequency; see also “Keep / Adapt AWG
    Clock-Period” and the “Nearest AWG-Frequency [Hz]”. The Desired AWG-Frequency [Hz]
    is a floating-point number in the range between 0.001 Hz and 10’000 Hz; the decimal
    point must be a period (point).
    At the maximum Desired AWG-Frequency of 10’000 Hz (period 100 μsec) the Standard
    Waveform consists of 10 points at an AWG Clock-Period of 10 μsec.
    @freq - floating point number specifying frequency in Hz
    """
    def read_SWGDesFrequency(self):
        return self.write("C SWG DF?")

    def write_SWGDesFrequency(self, freq):
        return self.write("C SWG DF {}".format(freq))
    """
    Read or write the Boolean parameter Keep/Adapt AWG Clock-Period. To reach the
    Desired AWG-Frequency as close as possible, select Adapt AWG Clock-Period.
    If Adapt AWG Clock-Period (1) is selected, the AWG Clock-Period gets adapted to meet the
    Desired AWG Frequency as close as possible. The update of the AWG Clock-Period on the
    corresponding DAC-Board (Lower or Higher) is automatically done, when the Wave-
    Memory is written to the AWG-Memory; see AWG Clock-Period [μsec] in the AWG
    CONTROL Commands.
    If Keep AWG Clock-Period (0) is selected, the AWG Clock-Period of the corresponding
    DAC-Board (depending on the Selected Wave-Memory A/B/C/D) is read and used for the
    waveform generation. At the standard AWG Clock-Period of 10 μsec the minimal AWG
    Frequency is 2.941 Hz; this is given by the maximum AWG-Memory Size of 34’000 points
    times the AWG Clock-Period of 10 μsec. Lower AWG frequencies can be reached by
    selecting higher AWG Clock-Periods.
    These two different options (Keep/Adapt AWG Clock-Period) can be written or readout:
    0=Keep AWG Clock-Period/1=Adapt AWG Clock-Period
    @mode - integer of adaptive clock mode, 0/1 (keep/adapt)
    """
    def read_SWGApdativeClk(self):
        return self.write("C SWG ACLK?")

    def write_SWGAdaptiveClk(self, mode):
        return self.write("C SWG ACLK {}".format(mode))
    """
    Read or write the Amplitude [Vp] parameter of the generated Standard Waveform. This
    value corresponds to the peak-voltage of the generated Standard Waveform. For
    Gaussian-Noise the Amplitude [Vp] corresponds to the RMS-value (Sigma). The
    Amplitude [Vp] is a floating-point number in the range between -50.000000 V and
    +50.000000 V; the decimal point must be a period (point). A negative Amplitude
    corresponds to a shift in Phase [°] of 180°. The ±50 V range in Amplitude [Vp] extends the
    flexibility in generating clipping-waveforms, also by applying a DC-Offset Voltage.
    @voltage - floating point number specifying the Vp parameter
    """
    def read_SWGAmplitude(self):
        return self.write("C SWG AMP?")

    def write_SWGAmplitude(self, voltage):
        return self.write("C SWG AMP {}".format(voltage))
    """
    Read or write the DC-Offset Voltage [V] parameter of the generated Standard Waveform.
    The DC-Offset Voltage is added to the function and therefore shifts the waveform in the
    amplitude. If "DC-Voltage only" is selected as function, this parameter is used as fixed DC-
    Voltage.
    The DC-Offset Voltage is a floating-point number in the range between -10.000000 V and
    +10.000000 V; the decimal point must be a period (point)
    @voltage - floating point number specifying the DC offset voltage
    """
    def read_SWGDCOffset(self):
        return self.write("C SWG DCV?")

    def write_SWGDCOffset(self, voltage):
        return self.write("C SWG DCV {}".format(voltage))
    """
    Read or write the Phase [°] parameter of the generated Standard Waveform. The Phase
    shifts the generated waveform in time; it isn’t applicable for Gaussian-Noise, Ramp and
    DC-Voltage only. A Sine with a Phase of 90° corresponds to a Cosine.
    The Phase [°] is a floating-point number in the range between -360.0000° and
    +360.0000°; the decimal point must be a period (point).
    @angle - floating point number indicating the phase angle
    """
    def read_SWGPhase(self):
        return self.write("C SWG PHA?")

    def write_SWGPhase(self, angle):
        return self.write("C SWG PHA {}".format(angle))
    """
    Read or write the Duty-Cycle [%] parameter for the generation of the Pulse-Waveform.
    The Duty-Cycle is only applicable for the Pulse function. A 50% Duty-Cycle results in a
    Square Wave; the higher the Duty-Cycle [%] the longer a high-level is applied.
    The Duty-Cycle [%] is a floating-point number in the range between 0.000% and
    100.000%; the decimal point must be a period (point).
    @dc - floating point number specifying the duty cycle percent
    """
    def read_SWGDutyCycle(self):
        return self.write("C SWG DUC?")

    def write_SWGDutyCycle(self, dc):
        return self.write("C SWG DUC {}".format(dc))
    """
    Read the Wave-Memory Size of the generated Standard Waveform. This Wave-Memory
    Size will also be the AWG-Memory Size, after writing to the AWG-Memory. The Wave-
    Memory Size is an integer number in the range from 10 to 34’000 and is calculated from
    the Desired Frequency [Hz] parameters of the Standard Waveform Generation.
    At the maximum frequency of 10’000 Hz a minimum Wave-Memory Size of 10 is reached
    while the AWG Clock-Period must be 10 μsec. Each point of the Wave-Memory
    corresponds to a DAC-Voltage in a range of ±10 V
    """
    def read_SWGMemSize(self):
        return self.write("C SWG MS?")
    """
    Read the Nearest AWG-Frequency [Hz] which can be reached as close as possible to the
    Desired AWG-Frequency [Hz]; is a floating-point number in the range between 0.001 Hz
    and 10’000 Hz.
    If it must be optimized, select "Adapt AWG-CLK" (see above). Not all desired AWG-
    Frequencies can be achieved, since the AWG-Clock Period can only be adjusted with a
    resolution of 1 μsec.
    """
    def read_SWGNearestFreq(self):
        return self.write("C SWG NF?")
    """
    Read the Waveform Clipping Status of the Generated Standard Waveform (SWG). If the
    amplitude of the generated waveform exceeds the maximum voltage of ± 10 V anywhere,
    the Clipping is set (1). If the Amplitude is always within the ± 10 V range (which means
    OK), the Clipping is not reset (0).
    0=Not Clipping/1=Clipping
    """
    def read_SWGClippingStatus(self):
        return self.write("C SWG CLP?")
    """
    Read the SWG/AWG Clock-Period [μsec] (10....4E9), which was used for the Standard
    Waveform Generation (SWG). This integer number represents the AWG Clock-Period in
    μsec (1E-6 sec) and the resolution is 1 μsec. If “Keep AWG Clock-Period” is selected, the
    AWG Clock-Period of the corresponding DAC-Board is read. If “Adapt AWG Clock-Period”
    is selected, the SWG/AWG Clock-Period is adapted to meet the Desired AWG Frequency
    as close as possible.
    """
    def read_SWGClkPeriod(self):
        return self.write("C SWG CP?")
    """
    Read or write the Selected Wave-Memory (WAV-A/B/C/D) to which the Wave-Function
    will be applied. If Keep AWG Clock-Period is selected above, the AWG Clock-Period of the
    corresponding DAC-Board is read: From the Lower DAC-Board if Wave-Memory A or B is
    selected and from the Higher DAC-Board if Wave-Memory C or D is selected.
    @mem - integer specifying the WAV memory, 0/1/2/3 (A/B/C/D)
    """
    def read_SWGMemSelected(self):
        return self.write("C SWG WMEM?")

    def write_SWGMemSelected(self, mem):
        return self.write("C SWG WMEM {}".format(mem))
    """
    Read or write the Selected Wave-Function which will be applied on the generated
    Standard Waveform and the Selected Wave-Memory when “Apply to Wave-Memory Now”
    is operated.
    The following Wave-Functions are available: COPY, APPEND, SUM, MULTIPLY and
    DIVIDE. When COPY Waveform is selected, the actual Wave-Memory is overwritten. The
    other four Wave-Functions can be applied to START or to the END of Wave-Memory.
    With these Wave-Functions complex and user-specific waveforms can be created in the
    Wave-Memory. Multiple Wave-Functions can be applied on different generated Standard
    Waveforms to reach the desired user-specific waveform.
    These nine different Wave-Functions are available and are represented by the following
    integer numbers:
    0 = COPY to Wave-MEM -> Overwrite
    1 = APPEND to Wave-MEM @START
    2 = APPEND to Wave-MEM @END
    3 = SUM Wave-MEM @START
    4 = SUM Wave-MEM @END
    5 = MULTIPLY Wave-MEM @START
    6 = MULTIPLY Wave-MEM @END
    7 = DIVIDE Wave-MEM @START
    8 = DIVIDE Wave-MEM @END
    @func - integer specifying the function to perform, 0/1/2/3/4/5/6/7/8 (see above for coding scheme)
    """
    def read_SWGSelectedFunc(self):
        return self.write("C SWG WFUN?")

    def write_SWGSelectedFunc(self, func):
        return self.write("C SWG WFUN {}".format(func))
    """
    Read or write the Boolean parameter No Linearization/Linearization for actual DAC-
    Channel. When “Copy to Wave-Memory Now” is performed, the actual selected AWG DAC-
    Channel gets registered for the later linearization when the WAV-Memory is written to
    the AWG-Memory. In this case the AWG-Waveform gets also linearized after applying the
    polynomial. If No Linearization is selected the DAC-Channel is registered as a zero (0)
    which indicates that no linearization will be done when the WAV-Memory is written to
    the AWG-Memory; this slightly increases the write performance.
    These two different options (No Linearization/Linearization for actual DAC-Channel) can
    be written or readout:
    0=No Linearization/1=Linearization for actual DAC-Channel
    @mode - integer specifying linearization mode, 0/1 (no lin/lin)
    """
    def read_SWGLinearization(self):
        return self.write("C SWG LIN?")

    def write_SWGLinearization(self, mode):
        return self.write("C SWG LIN {}".format(mode))
    """
    The Selected Wave-Function gets applied to the Selected Wave-Memory (WAV-A/B/C/D).
    At this moment, the actual selected AWG DAC-Channel gets registered if “Linearization for
    actual DAC-Channel” is selected (see above). After setting this control, it gets reset
    internally.
    """
    def apply_SWGFunction(self):
        return self.write("C SWG APPLY")
    



######################################################################################

#                  WAVE CONTROL COMMANDS

######################################################################################
    """
    Read the Size of one of the five Wave-Memories (WAV-A/B/C/D/S). This Wave-Memory
    Size will also be the AWG-Memory Size, after writing to the AWG-Memory. The Wave-
    Memory Size is an integer number in the range from 0 to 34’000. A Wave-Memory Size of
    zero (0) indicates that this Wave-Memory is cleared.
    Note: For optimal performance, keep the Wave-Memory Size as small as possible and
    always clear unused Wave-Memories.
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def read_WAVMemSize(self, mem):
        return self.write("C WAV-{} MS?".format(mem))
    """
    Clear the selected Wave-Memory (WAV-A/B/C/D/S) and set the Wave-Memory Size to
    zero (0). The WAV-S is the Saved Waveform. After setting this control, it gets reset
    internally
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def clear_WAVMem(self, mem):
        return self.write("C WAV-{} CLR".format(mem))
    """
    Save the selected Wave-Memory (WAV-A/B/C/D) to the internal volatile memory on the
    LNHR DAC II; it is called WAV-S.
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def save_WAVMem(self, mem):
        return self.write("C WAV-{} SAVE".format(mem))
    """
    Read the corresponding DAC-Channel for the Linearization of one of the four Wave-
    Memories (WAV-A/B/C/D). The Linearization for this DAC-Channel is done when the
    Wave-Memory is written to the AWG-Memory. If "No Linearization" was selected when
    the waveform was copied to the Wave-Memory, the corresponding DAC-Channel is 0
    (zero). The DAC-Channel for Linearization is an integer number in the range from 0 to 24;
    the not existing DAC-Channel 0 (zero) means that no linearization gets applied.
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def read_WAVMemLinChannel(self, mem):
        return self.write("C WAV-{} LINCH?".format(mem))
    """
    Write the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory (AWG-
    A/B/C/D). After setting this control, it gets reset internally. The Polynomial is only applied
    when the corresponding Boolean parameter "Apply Polynomial" is selected (see chapter
    “2D-Scan CONTROL Commands”).
    Note: The Saved Waveform (WAV-S) has first to be copied to one of the four Wave-
    Memories (WAV-A/B/C/D) before it can be written to the corresponding AWG-Memory.
    To recalled the Saved Waveform (WAV-S) select “Use Saved Waveform” in the SWG Mode
    selection
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def write_WAVMemToAWGMem(self, mem):
        return self.write("C WAV-{} WRITE".format(mem))
    """
    During writing the Wave-Memory (WAV-A/B/C/D) to the corresponding AWG-Memory
    (AWG-A/B/C/D) this Busy flag is set (1); if it is Idle state the value is zero (0).
    0=Idle/1=Busy (writing WAV- to AWG-Memory
    @mem - character indicating the wave memory, A/B/C/D/S 
    """
    def read_WAVBusyWriting(self, mem):
        return self.write("C WAV-{} BUSY?".format(mem))


####################################################################

#               SPECIAL AND COMPOUND FUNCTIONS

####################################################################

    """
    Creates a linear scan of the given parameter (for example a DAC channel), from a START value
    to a STOP value, with num_points pauses/measurements. A time delay is made before a measured 
    dependent parameter is read and stored into a list.  The list is returned after the scan.
    @param - the independent parameter.  Must have a set() method
    @start - the starting value for the scan
    @stop - the stopping value for the scan
    @num_points - the number of points within the scan.
    @delay - the time to pause at each point before reading any dependent parameters.
    @measured_param - the dependent parameter to measure.  Must have a get() method.
    """
    def scan1D(self, param, start, stop, num_points, delay, measured_param):
        data = [] 
        increment = (stop - start) / (num_points-1)
        current = start
        
        values = []
        for i in range(num_points - 1):
            values.append(current)
            current += increment
        values.append(stop)
        for val in values:
            param.set(val)
            time.sleep(delay)
            m = measured_param.get()
            print(m)
            data.append(m)
        return data


    """
    Creates a 2D linear scan of two independent parameters.  The "outer-loop" parameter is param1, and runs through it's
    scan only once. The "inner-loop" parameter, param2, runs through a scan each time param1 steps. At each step, 
    the dependent parameters, stored in a list, are read and recorded.
    @param1 - the independent outer-loop parameter.  Must have a set() method
    @start1 - the starting value for the outer scan
    @stop1 - the stopping value for the outer scan
    @num_points1 - the number of points within the outer scan.
    @delay1 - the time to pause at each point of the outer scan before reading any dependent parameters.
    @param2 - the independent inner-loop parameter.  Must have a set() method
    @start2 - the starting value for the inner scan
    @stop2 - the stopping value for the inner scan
    @num_points2 - the number of points within the inner scan.
    @delay2 - the time to pause at each point of the inner scan before reading any dependent parameters.
    @measured_params_list - a list of dependent parameters. Each must have a get() method
    """
    def scan2D(self, param1, start1, stop1, num_points1, delay1, param2, start2, stop2, num_points2, delay2, measured_params_list):
        data = [] # return variable
        increment1 = (stop1 - start1) / (num_points1 - 1)
        increment2 = (stop2 - start2) / (num_points2 - 1)

        current1 = start1
        current2 = start2
        values1 = []
        values2 = []
        for i in range(num_points1 - 1):
            values1.append(current1)
            current1 += increment1
        values1.append(stop1)
        for i in range(num_points2 - 1):
            values2.append(current2)
            current2 += increment2
        values2.append(stop2)
        
        for val1 in values1:
            param1.set(val1)
            time.sleep(delay1)
            line_data = []
            for val2 in values2:
                param2.set(val2)
                time.sleep(delay2)
                data_point = []
                for p in measured_params_list:
                    data_point.append(p.get())
                line_data.append(tuple(data_point))
            # append data list for scan line into return variable
            data.append(line_data)
        return data

    def handleDACSetErrors(code):
        num = int(code)
        if num == 0:
            return num
        elif num == 1:
            print("Invalid DAC-Channel")
        elif num == 2:
            print("Missing DAC-Value, Status or BW")
        elif num == 3:
            print("DAC-Value out of range")
        elif num == 4:
            print("Mistyped")
        elif num == 5:
            print("Writing not allowed (Ramp/Step-Generator or AWG are running on this DAC-Channel)")
        return num

    def handleAWGSetErrors(code):
        num = int(code)
        if num == 0:
            return num
        if num == 1:
            print("Invalid AWG-Memory")
        elif num == 2:
            print("Missing AWG-Address and/or AWG-Value")
        elif num == 3:
            print("AWG-Address and/or AWG-Value out of range")
        elif num == 4:
            print("Mistyped")
        return num

    def handleWAVSetErrors(code):
        num = int(code)
        if num == 0:
            return num
        if num == 1:
            print("Invalid WAV-Memory")
        elif num == 2:
            print("Missing WAV-Address and/or WAV-Voltage")
        elif num == 3:
            print("WAV-Address and/or WAV-Voltage out of range")
        elif num == 4:
            print("Mistyped")
        return num

    def handlePOLYSetErors(code):
        num = int(code)
        if num == 0:
            return num
        if num == 1:
            print("Invalid Polynomial Name")
        elif num == 2:
            print("Missing Polynomial Coefficient(s)")
        elif num == 4:
            print("Mistyped")
        return num
    
    """
    After each CONTROL Write command, an error code will be returned.  '0' indicates no error. 
    If you want an interpretation printed to standard output, pass the code into this method.
    Additional actions should be taken in the code surrounding the write function.
    You should at least check for '0', to know that your program can continue running normally.
    """
    def handleCONTROLWriteErrors(code):
        num = int(code)
        if num == 0:
            return num
        if num == 1:
            print("Invalid DAC-Channel")
        elif num == 2:
            print("Invalid Parameter")
        elif num == 4:
            print("Mistyped")
        elif num == 5:
            print("Writing not allowed")




# %%
