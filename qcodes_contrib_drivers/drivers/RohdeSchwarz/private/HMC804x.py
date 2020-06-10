from qcodes import VisaInstrument, validators as vals
from qcodes import InstrumentChannel, ChannelList


class RohdeSchwarzHMC804xChannel(InstrumentChannel):
    def __init__(self, parent, name, channel):
        super().__init__(parent, name)

        select_cmd = ":INSTrument:NSELect {};".format(channel)
        self.channel = channel
        self.add_parameter("set_voltage",
                           label='Target voltage output',
                           set_cmd="{} :SOURce:VOLTage:LEVel:IMMediate:AMPLitude {}".format(
                               select_cmd, '{}'),
                           get_cmd="{} :SOURce:VOLTage:LEVel:IMMediate:AMPLitude?".format(
                               select_cmd),
                           get_parser=float,
                           unit='V',
                           vals=vals.Numbers(0, 32.050)
                          )
        self.add_parameter("set_current",
                           label='Target current output',
                           set_cmd="{} :SOURce:CURRent:LEVel:IMMediate:AMPLitude {}".format(
                               select_cmd, '{}'),
                           get_cmd="{} :SOURce:CURRent:LEVel:IMMediate:AMPLitude?".format(
                               select_cmd),
                           get_parser=float,
                           unit='A',
                           vals=vals.Numbers(0.5e-3, self._parent.max_current)
                           )
        self.add_parameter('state',
                           label='Output enabled',
                           set_cmd='{} :OUTPut:CHANnel:STATe {}'.format(select_cmd, '{}'),
                           get_cmd='{} :OUTPut:CHANnel:STATe?'.format(select_cmd),
                           val_mapping={'ON': 1, 'OFF': 0},
                           vals=vals.Enum('ON', 'OFF')
                           )
        self.add_parameter("voltage",
                           label='Measured voltage',
                           get_cmd="{} :MEASure:SCALar:VOLTage:DC?".format(
                               select_cmd),
                           get_parser=float,
                           unit='V',
                          )
        self.add_parameter("current",
                           label='Measured current',
                           get_cmd="{} :MEASure:SCALar:CURRent:DC?".format(
                               select_cmd),
                           get_parser=float,
                           unit='A',
                           )
        self.add_parameter("power",
                           label='Measured power',
                           get_cmd="{} :MEASure:SCALar:POWer?".format(
                               select_cmd),
                           get_parser=float,
                           unit='W',
                           )

        self.add_parameter("smrt_current",
                           label='Set current',
                           set_cmd=self._set_smrt_current,
                           get_cmd=self._get_smrt_current,
                           unit='A',
                           )

    def _set_smrt_current(self, i):
        ''' Set the current, smartly.
        for i=0, set voltage=0
        for i > 0.5e-3, set voltage=max and set the current

        command:
        APPLy {<Voltage>|DEF|MIN|MAX} 
                [,{<Current>|DEF|MIN|MAX}][,{OUT1|OUT2|OUT3}]
        '''
        if i <= 0.5e-3 : 
            self.write_raw(f"APPLy 0,0.5e-3,OUT{self.channel}")
        else :
            self.write_raw(f"APPLy MAX,{i},OUT{self.channel}")

    def _get_smrt_current( self ):
        ''' Get the set smart current
        '''
        if self.set_voltage() == 0:
            return 0
        else:
            return self.set_current()

class RohdeSchwarzHMC804xBIP(InstrumentChannel):
    """ Support for bipolar output hack: 
        use one channel for positive polarity, use another for negative polarity.
        atomatically handle crossovers by turning off/activating the appropriate channel
    """
    def __init__( self, parent, name, pos_channel : RohdeSchwarzHMC804xChannel, 
            neg_channel : RohdeSchwarzHMC804xChannel ):
        """ pos_channel: e.g. RohdeSchwarzHMC8043.ch1, channel to use for positive polarity
        neg_channel: e.g. RohdeSchwarzHMC8043.ch1,, channel to use for negative polarity
        """
        super().__init__(parent, name)

        self.pos_channel = pos_channel
        self.neg_channel = neg_channel

        self.add_parameter("set_voltage",
                           label='Target voltage output',
                           set_cmd=self._set_voltage,
                           get_cmd=self._get_voltage,
                           get_parser=float,
                           unit='V',
                           vals=vals.Numbers(-32.050, 32.050)
                          )

        self.add_parameter("voltage",
                           label='Measured voltage',
                           get_cmd=self._voltage,
                           get_parser=float,
                           unit='V',
                          )

        self.add_parameter("set_current",
                           label='Target current output',
                           set_cmd=self._set_current,
                           get_cmd=self._get_current,
                           get_parser=float,
                           unit='A',
                           vals=vals.Numbers(-1*self._parent.max_current, self._parent.max_current)
                           )

        self.add_parameter("current",
                           label='Measured current',
                           get_cmd=self._current,
                           get_parser=float,
                           unit='A',
                           )

    def _set_current( self, i ):
        """ Set current. If > 0, set neg_channel to zero and turn off.
        then set pos_channel
        """
        if i > 0 :
            self._zero_and_off( self.neg_channel )
            self.pos_channel.smrt_current(i)
            self.pos_channel.state('ON')
        elif i < 0 :
            self._zero_and_off( self.pos_channel )
            self.neg_channel.smrt_current(abs(i))
            self.neg_channel.state('ON') 
        elif i == 0 : # both outputs off
            self._zero_and_off( self.pos_channel )
            self._zero_and_off( self.neg_channel )

    def _get_current( self ):
        """ Get the current
        """
        chan, sign = self._active_chan()
        if chan is None :
            return 0
        else :
            return sign * chan.smrt_current()

    def _current( self ):
        """ Get the measured current
        """
        chan, sign = self._active_chan()
        if chan is None :
            return 0
        else :
            return sign * chan.current()

    def _voltage( self ):
        ''' Return measured voltage '''
        chan, sign = self._active_chan()
        if chan is None :
            raise ValueError( "No channel is turned on. Voltage unknown.")
        else :
            return sign * chan.voltage()

    def _set_voltage( self, v ) :
        ''' Set voltage. If > 0, set neg_channel to zero and turn off.
        then set pos_channel '''

        if v >= 0 :
            self._zero_and_off( self.neg_channel )
            self.pos_channel.set_voltage(v)
            self.pos_channel.state('ON')
        elif v < 0 :
            self._zero_and_off( self.pos_channel )
            self.neg_channel.set_voltage(abs(v))
            self.neg_channel.state('ON')

    def _get_voltage( self ) :
        ''' Get voltage
        '''

        chan, sign = self._active_chan()
        if chan is None :
            raise ValueError( "No channel is turned on. Voltage unknown.")

        return sign * chan.set_voltage()

    def _active_chan( self ):
        """ Get the active channel. and the sign (if its positive or negative)
        Check that one and only one channel is turned on
        """
        sp = self.pos_channel.state() is 'ON'
        sm = self.neg_channel.state() is 'ON'
        if sm and sp :
            raise ValueError( 'Both channels are on.' )
        if not (sm or sp) :
            return None, 1
        if sp :
            return self.pos_channel, 1
        if sm :
            return self.neg_channel, -1

    def _zero_and_off( self, channel : RohdeSchwarzHMC804xChannel ):
        """ Set channel to zero and turn it off
        """
        channel.set_voltage(0)
        channel.state('OFF')

class _RohdeSchwarzHMC804x(VisaInstrument):
    """
    This is the general HMC804x Power Supply driver class that implements shared parameters and functionality
    among all similar power supply from Rohde & Schwarz.

    This driver was written to be inherited from by a specific driver (e.g. HMC8043).
    """

    _max_currents = {3: 3.0, 2: 5.0, 1: 10.0}

    def __init__(self, name, address, num_channels, **kwargs):
        super().__init__(name, address, **kwargs)

        self.max_current = _RohdeSchwarzHMC804x._max_currents[num_channels]

        self.add_parameter('state',
                           label='Output enabled',
                           set_cmd='OUTPut:MASTer:STATe {}',
                           get_cmd='OUTPut:MASTer:STATe?',
                           val_mapping={'ON': 1, 'OFF': 0},
                           vals=vals.Enum('ON', 'OFF')
                           )

        # channel-specific parameters
        channels = ChannelList(self, "SupplyChannel", RohdeSchwarzHMC804xChannel, snapshotable=False)
        for ch_num in range(1, num_channels+1):
            ch_name = "ch{}".format(ch_num)
            channel = RohdeSchwarzHMC804xChannel(self, ch_name, ch_num)
            channels.append(channel)
            self.add_submodule(ch_name, channel)
        channels.lock()
        self.add_submodule("channels", channels)
        # add bipolar virtual channel 1/2
        bip = RohdeSchwarzHMC804xBIP( self, 'bip', self.ch1, self.ch2 )
        self.add_submodule("bip", bip)
        self.connect_message()
