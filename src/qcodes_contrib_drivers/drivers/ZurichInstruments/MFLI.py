import numpy as np
from functools import partial
import logging
import typing as t

from py import process
log = logging.getLogger(__name__)

import time
import matplotlib.pyplot as plt
import numpy as np

import zhinst.utils
import qcodes as qc
from qcodes.instrument.base import Instrument
from zhinst.qcodes.session import ZISession
from qcodes.instrument import InstrumentChannel
import qcodes.utils.validators as vals
from zhinst.qcodes.driver.devices.base import ZIBaseInstrument

from qcodes.instrument.parameter import ParameterWithSetpoints, Parameter

from qcodes.dataset.measurements import Measurement, res_type, DataSaver
from qcodes.instrument.specialized_parameters import ElapsedTimeParameter

class MFLI(ZIBaseInstrument):
    """QCoDeS driver for the Zurich Instruments MFLI.

    Args:
        serial: Serial number of the device, e.g. *'dev12000'*.
            The serial number can be found on the back panel of the instrument.
        server_host: Host address of the data server (e.g. localhost)
        server_port: Port number of the data server. If not specified the session
            uses the default port. (default = 8004)
        interface: Device interface (e.g. = "1GbE"). If not specified
            the default interface from the discover is used.
        name: Name of the instrument in qcodes.
        raw: Flag if qcodes instance should only created with the nodes and
            not forwarding the toolkit functions. (default = False)
        new_session: By default zhinst-qcodes reuses already existing data
            server session (within itself only), meaning only one session to a
            data server exists. Setting the flag will create a new session.
        allow_version_mismatch: if set to True, the connection to the data-server
            will succeed even if the data-server is on a different version of LabOne.
            If False, an exception will be raised if the data-server is on a
            different version. (default = False)

    Warning:
        Creating a new session should be done carefully and reusing
        the created session is not possible. Consider instantiating a
        new session directly.
    """

    def __init__(
        self,
        serial: str,
        host: str,
        port: int = 8004,
        *,
        interface: t.Optional[str] = None,
        name=None,
        raw=False,
        new_session: bool = False,
        allow_version_mismatch: bool = False,
    ):
        session = ZISession(host, port, hf2=False, new_session=new_session)
        tk_device = session.toolkit_session.connect_device(serial, interface=interface)
        super().__init__(tk_device, session, name=name, raw=raw)
        session.devices[self.serial] = self

        daq_module = self.session.modules.daq
        daq_module.set('device', self.serial)
        self.daq_module = daq_module

        self.add_parameter( 'spectrum_samplecount',
                unit='',
                label='number of points',
                set_cmd = partial(self.daq_module.grid.set, 'cols'),
                get_cmd = partial(self.daq_module.grid.get, 'cols')
            )

        self.add_parameter( 'spectrum_repetitions',
            unit='',
            label='number of spectra to acquire',
            initial_value = 1,
            set_cmd = partial(self.daq_module.grid.set, 'repetitions'),
            get_cmd = partial(self.daq_module.grid.get, 'repetitions')
        )

        self.add_parameter( 'spectrum_span',
            unit='Hz',
            label='spectrum frequency span',
            set_cmd=partial(self.daq_module.spectrum.set, 'frequencyspan'),
            get_cmd= partial(self.daq_module.spectrum.get, 'frequencyspan')
        )
        
        self.add_parameter('spectrum_duration',
            unit='s',
            label='spectrum duration',
            set_cmd= partial(self.daq_module.set, 'duration'),
            get_cmd=partial(self._daq_module_get, 'duration')
        )

        self.add_parameter( 'spectrum_frequency',
            unit='Hz',
            label= 'Frequency',
            snapshot_value=False,
            get_cmd= self._get_spectrum_frequency,
            vals=vals.Arrays(shape=(self._spectrum_freq_length,))
        )

        self.add_parameter( 'spectrum_power',
            unit='$\mathrm{V}^2$/Hz',
            label='Power spectral density',
            parameter_class = ParameterWithSetpoints,
            setpoints = (self.spectrum_frequency,),
            get_cmd = self._get_spectrum_power,
            vals=vals.Arrays(shape=(self._spectrum_freq_length,)))

    def _get_spectrum_power(self):
        # Divide out the filter transfer function from the (averaged) absolute FFT of the spectrum.
        compensated_samples = self.spectrum_samples.value[0] / self.spectrum_filter.value[0]
        # convert compensated FFT to PSD by squaring and normalizing by frequency bin width
        return np.power(compensated_samples, 2) / self.spectrum_samples.header['gridcoldelta'][0]
        
    def _spectrum_freq_length(self):
        return len(self.spectrum_samples.value[0])

    def _get_spectrum_frequency(self):
        bin_count = len(self.spectrum_samples.value[0])
        bin_resolution = self.spectrum_samples.header['gridcoldelta'][0]
        center_freq = self.spectrum_samples.header['center'][0]
        frequencies = np.arange(bin_count)

        bandwidth = bin_resolution * len(frequencies)
        frequencies = center_freq + (
        frequencies * bin_resolution - bandwidth / 2.0 + bin_resolution / 2.0)
        return frequencies
    
    def _daq_module_get(self, name):
        path = name.split('/')
        param = self.daq_module.get(name)
        for i in path:
            param = param[i]
        return param[0]


    def trigger_spectrum(self, subscribed_paths = ("sample.xiy.fft.abs.filter", "sample.xiy.fft.abs.avg") ):
        """
        Default things to subscribe:
        sample.xiy.fft.abs.filter
        sample.xiy.fft.abs.avg
        """
        daq_module = self.daq_module
        #self.snapshot(update=True)
        daq_module.set('device', self.serial)
        daq_module.set("type", 0) # continuous triggering
        daq_module.grid.set("mode", 4) 
        daq_module.grid.set("rows", 1) 
        daq_module.set("count", 1) # number of triggers
        daq_module.grid.set("cols", self.spectrum_samplecount())
        daq_module.grid.set('repetitions', self.spectrum_repetitions())
        daq_module.spectrum.set("frequencyspan", self.spectrum_span())
        
        for p in subscribed_paths :
            path = f"/{self.serial}/demods/0/{p}" # .pwr?
            daq_module.subscribe(path)
            daq_module.spectrum.set("autobandwidth", 1)
            daq_module.spectrum.set('enable', 1)
        daq_module.execute()

        start = time.time()
        timeout = 60000  # [s]

        while not daq_module.finished():
            time.sleep(0.2)
            if (time.time() - start) > timeout:
                print("\ndaqModule still not finished, forcing finish...")
                daq_module.finish()

        data = daq_module.read() # True
        self.spectrum_filter = data[f"/{self.serial}/demods/0/sample.xiy.fft.abs.filter"][0]
        self.spectrum_samples = data[f"/{self.serial}/demods/0/sample.xiy.fft.abs.avg"][0]

        for p in subscribed_paths:
            daq_module.unsubscribe(path)