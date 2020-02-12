import matplotlib.pyplot as plt
from qcodes.instrument.base import Instrument
import numpy as np
import qcodes as qc
import os
import qcodes.instrument_drivers.labbrick.lowlevel.lms as lms
from qcodes.instrument_drivers.labbrick.lowlevel.lms import default_library_location, download_lms_binaries
from qcodes.instrument_drivers.labbrick.lowlevel.lms import VNXError

api = lms.VNX_LSG_API.default()

class LbB(Instrument):    
    
    @classmethod
    def are_u_there(cls):
    # Check for DLL, if not there download
        if not lms.default_library_location():
            lms.download_lms_binaries()        
    
    @classmethod
    def fint_stuffs(cls):
        api = lms.VNX_LSG_API.default()
        for device_id in api.get_dev_info():
            print('There are', api.get_num_devices(), 'device(s) connected:')
            print(api.get_serial_number(device_id),
                  api.get_model_name(device_id),
                  lms.LSGStatus(api.get_device_status(device_id)))
        return api
    
    def __init__(self, name, device_id=1, api=None):
        
        self.ffudge = 1e-1 # Units in Hz
        
        if not api:
            self.api = lms.VNX_LSG_API.default()
        else:
            self.api = api
            
        self._device_id = device_id
        
        #Has to be there because otherwise get_model_name won't work :(
        _ = self.api.get_num_devices()
        
        try:
            self.api.init_device(self._device_id)
        except VNXError:
            pass            
        
        super().__init__(name)
        
        self.add_parameter(name='set_test_mode',
                           label = 'Test Mode',
                           set_cmd=lambda on : self.api.set_test_mode(bool(on))                           
                          )
        
        self.add_parameter(name='get_model_name',
                          label='Model Name',
                          get_cmd=lambda : self.api.get_model_name(self._device_id)
                          )
        
        self.add_parameter(name='rf_on',
                          label='RF ON',
                          get_cmd=lambda : self.api.get_rf_on(self._device_id),                          
                          set_cmd=lambda on: self.api.set_rf_on(self._device_id, bool(on))
                          )
        
        self.add_parameter(name='get_device_info',
                           label='Device Info',
                           get_cmd= lambda : self.api.get_dev_info()
                          ) 
        
        self.add_parameter(name='init_device',
                           label='Initialize Device',
                           get_cmd=lambda : self.api.init_device(self._device_id)
                          ) #it returns 0
        
        self.add_parameter(name='close_device',
                           label='Close Device',
                           get_cmd=lambda : self.api.close_device(self._device_id)
                          ) #it returns 0
        
        self.add_parameter(name='get_dll_version',
                           label='DLL Version',
                           get_cmd=lambda : self.api.get_dll_version()
                          )
        
        self.add_parameter(name='use_internal_ref',
                          label='Use Internal Reference',
                          get_cmd=lambda : self.api.get_use_internal_ref(self._device_id),
                          set_cmd=lambda on : self.api.set_use_internal_ref(self._device_id, bool(on))
                          )
        
        self.add_parameter(name='increasing_freq_sweep',
                          label='Set Frequency Sweep Direction',
                          set_cmd=lambda on: self.api.set_sweep_direction(self._device_id, bool(on))
                          )
        
        self.add_parameter(name='get_device_status',
                          label='Device Status',
                          get_cmd=lambda : self.api.get_device_status(self._device_id)
                          )
        
        self.add_parameter(name='get_serial_number',
                          label='Serial Number',
                          get_cmd=lambda : self.api.get_serial_number(self._device_id)
                          )
        
        self.add_parameter(name='start_sweep',
                          label='Start Sweep',
                          set_cmd= lambda go : self.api.start_sweep(self._device_id, bool(go))
                          )
                
        self.add_parameter(name='frequency',
                          label='Frequency',
                          unit='Hz',
                          get_cmd=lambda : self.api.get_frequency(self._device_id)/self.ffudge,
                          set_cmd=lambda f : self.api.set_frequency(self._device_id, int(f * self.ffudge))
                          ) #in Hz
        
        self.add_parameter(name='power',
                          label='Power',
                          unit='dBm',
                          get_cmd=lambda : 10-(self.api.get_power_level(self._device_id))/4,
                          set_cmd=lambda p : self._power_set(int(p*4))
                          )
        
        self.add_parameter(name="sweepmode_on",
                          label="Sweep Mode",
                          set_cmd=lambda on : self.api.set_sweep_mode(self._device_id, bool(on))
                          )
        
        self.add_parameter(name='start_frequency',
                          label='Start Frequency',
                          unit='Hz',
                          get_cmd=lambda : self.api.get_start_frequency(self._device_id)/self.ffudge,
                          set_cmd=lambda f : self._freq_set_start(int(f * self.ffudge))
                          ) #in Hz
        
        self.add_parameter(name='end_frequency',
                          label='End Frequency',
                          unit='Hz',
                          get_cmd=lambda : self.api.get_end_frequency(self._device_id)/self.ffudge,
                          set_cmd=lambda f : self._freq_set_end(int(f * self.ffudge))
                          ) #in Hz  
        
        self.add_parameter(name='max_frequency',
                          label='Maximum Frequency',
                          unit='Hz',
                          get_cmd=lambda : self.api.get_max_freq(self._device_id)/self.ffudge
                          ) #in Hz
        
        self.add_parameter(name='min_frequency',
                          label='Minimum Frequency',
                          unit='Hz',
                          get_cmd=lambda : self.api.get_min_freq(self._device_id)/self.ffudge
                          ) #in Hz
        
        self.add_parameter(name='max_power',
                          label='Maximum Power',
                          unit='dBm',
                          get_cmd=lambda : self.api.get_max_pwr(self._device_id)/4
                          )
        
        self.add_parameter(name='min_power',
                          label='Minimum Power',
                          unit='dBm',
                          get_cmd=lambda : self.api.get_min_pwr(self._device_id)/4
                          )
    
    def _freq_set_start(self, f):
        if ((self.api.get_min_freq(self._device_id) <= f and f <= api.get_max_freq(self._device_id))):
            self.sweepmode_on(True)
            self.api.set_start_frequency(self._device_id, int(f))
        else:
            print("Start frequency value out of range.")
    
    def _freq_set_end(self, f):
        if ((self.api.get_min_freq(self._device_id) <= f and f <= api.get_max_freq(self._device_id))):
            self.sweepmode_on(True)
            self.api.set_end_frequency(self._device_id, int(f))
        else:
            print("End frequency value out of range.")        
        
    def _power_set(self, p):
        min_pwr = self.api.get_min_pwr(self._device_id)
        max_pwr = self.api.get_max_pwr(self._device_id)
        if ((min_pwr < p) and (p < max_pwr)):
            self.api.set_power_level(self._device_id, int(p))
        else:
            print("Power value out of range. \n Max: " + str(max_pwr/4) + "Min: " + str(min_pwr/4))