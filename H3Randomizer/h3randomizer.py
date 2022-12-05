import random
import time
from datetime import datetime
import threading
import pymem.process
from pymem import Pymem
import pymem.exception
from pymem.ressources.structure import MODULEINFO

import PyDebugger_CPP
from mainwindow import *
import logging

class Palette:
    level: str = "" # level this palette is instantiated for
    values = [] # list of values as int
    
    def __init__(self, l, vals):
        self.values = []
        self.level = l
        for val in vals:
            self.values.append(int(val)) # Add each value to the values array as an integer

    def __repr__(self):
        out = f"Palette(level: {self.level}, values({len(self.values)}): {self.values_as_hex()})"
        return out

    def values_as_hex(self): # Get a list of the values as hexadecimal strings
        out = []
        for val in self.values:
            out.append(hex(val).upper().replace('X', 'x'))
        return out

    def remove(self, value: int):
        """Removes a value from the Palette"""
        if value in self.values:
            self.values.remove(value)
        else:
            msg = f"{value} is not in the Palette!"
            print(msg)
            logging.error(msg)

    def add(self, value: int):
        """Adds a value to the Palette"""
        if value not in self.values:
            self.values.append(value)
        else:
            msg = f"{value} is already in the Palette!"
            print(msg)
            logging.error(msg)


class Game: # Abstraction for potential future randomizers
    p: Pymem = None
    base_mod: MODULEINFO = None
    game_dll: MODULEINFO = None
    exe_name: str = ""
    dll_name: str = ""
    cpp_accessor = None
    
    current_level: str = None # the current level updated every loop
    set_level: str = None # the set level for comparing to see if we're on a new level, set during initial_loop
    current_bsp: int = 0

    master_character_palette: Palette = None # A palette of all possible characters on a level
    master_weapon_palette: Palette = None # A palette of all possible weapons on a level

    weapon_palettes: dict = {}

    # TODO: Make these json and autoupdate
    charspawn_offsets = []
    charweapon_offsets = []
    curlevel_offsets = []
    curbsp_offsets = []
    string_dictionary_offsets = []
    special_offsets = [] # Multiple special offsets that are game-specific
    
    seed = 0 # this way we don't lose the original seed value for when game restarts or whatever
    
    ALLOWED_LEVELS = [] # String values of level names

    DISQUALIFIED_CHARACTERS = [] # Characters disqualified on all levels; automatically removed from character palette and will not be randomized
    DISQUALIFIED_WEAPONS = [] # Weapons disqualified on all levels; automatically removed from weapon palette and will not be randomized

    DISQUALIFIED_AREAS = [] # just crows for now

    CHARACTER_PALETTE_MODIFICATIONS = {}
    CHARACTER_PALETTE_BSP = {} # Only randomize these ones after the designated BSP

    WEAPON_PALETTE_MODIFICATIONS = {}
    WEAPON_PALETTE_BSP = {} # Only randomize these ones after the designated BSP

    WEAPON_CLASSES = {} # Map valid weapons to weapon classes
    WEAPON_CLASSES_MAPPING = {} # Map subclasses (tag names) to weapon_classes

    known_character_randomizations = {} # Randomizations that have already occured in this randomizer; ie. do not reroll when restart mission or revert checkpoint. {[SQ, SQ_IDX]: SAVED}
    known_weapon_randomizations = {} # Weapon randomizations that have already occured in this randomizer; {UID: SAVED}

    known_tag_strings = {} # Dictionary to store known tag strings

    def __init__(self, exe, dll):
        self.exe_name = exe
        self.dll_name = dll
        self.hooking_loop()
    
    def get_tag_string(self, datum, only_last: bool = True) -> str:    
        '''
        Returns the string of a given tag datum.
        '''
        if datum == 0x00000000 or datum == 0xFFFFFFFF:
            return "null"

        if datum in self.known_tag_strings:
            # If the datum is in our dictionary of known tag strings, just get it from there instead of rereading memory
            if only_last:
                # Return the last bit of the string after slash if only_last is True
                return self.known_tag_strings[datum].split("\\")[-1]
            return self.known_tag_strings[datum]

        i = datum % 0x10000     # Get the lower 4 bits of the tag datum
        i *= 8                  # Multiply by 8 (length of each string table entry)
        dict_base = self.get_pointer(self.game_dll, self.string_dictionary_offsets)
        ptr = self.p.read_ulonglong(dict_base + i) # string value can be found from the string dictionary base + the lower 4 bits of tag datum * 8

        try:
            out = self.p.read_string(ptr, 255) # read up to 255 characters or null terminator from the pointer
            if out:
                self.known_tag_strings[datum] = out
        except:
            msg = f"Could not get tag string of {hex(datum)}"
            print(msg)
            logging.error(msg)
            return "" # return blank string to hopefully not cause issues lmao

        if only_last:
            return out.split("\\")[-1] # if we're only getting the last part of the tag string, return the last bit of the string after a slash.

        return out # Read until string terminator or 255 bytes

    def get_pointer(self, module: MODULEINFO, offsets: list = [0]):
        '''
        Returns a pointer given a module (DLL) and list of offsets.
        '''

        base_offset: int = 0 # Initialize as 0 just in case

        if len(offsets) <= 1: # if we have one or less offset, just return the address + the first offset
            base_offset = offsets[0]
            return module.lpBaseOfDll + base_offset

        tmp_ptr: int = module.lpBaseOfDll + base_offset
        
        if len(offsets) > 1:
            for offset in offsets:
                if offset == offsets[-1]: # If it's the last offset just append to tmp_ptr
                    tmp_ptr += offset
                else: # Else keep adding offsets
                    tmp_ptr = self.p.read_longlong(tmp_ptr + offset)

        return tmp_ptr


    def update_current_level(self):
        '''
        Updates the current level variable.
        '''
        pointer = self.get_pointer(self.game_dll, self.curlevel_offsets) # get the current level pointer
        try:
            curlevel = self.p.read_string(pointer, 16) # read the level string from the current level pointer until 16 characters or null terminator
            self.current_level = curlevel
            return curlevel
        except:
            pass
        
    def update_current_bsp(self): # Potential todo: change this to zones for more accuracy
        '''
        Updates the current bsp variable.
        '''
        pointer = self.get_pointer(self.game_dll, self.curbsp_offsets) # get the current bsp pointer
        try:
            curbsp = self.p.read_int(pointer) # read the bsp integer
            self.current_bsp = curbsp
            return curbsp
        except:
            pass

    def hook(self, exe: str):
        """Continually attempt to get a handle of the defined process (exe). Returns Pymem object."""
        pm: Pymem = None
        while not pm: # Continually try to instantiate a new Pymem from the given exe name.
            try:
                pm = Pymem(exe) # try to create a Pymeme object from the exte name
                time.sleep(1)
            except Exception as e:
                if isinstance(e, pymem.exception.ProcessNotFound):
                    continue # continue if process isn't found
                elif isinstance(e, pymem.exception.CouldNotOpenProcess):
                    console_output(f"Failed to attach to {exe}.") # break if we fail to attach to the process
                    break
                else:
                    console_output(f"{e}") # print error if it's something else and break
                    break
            else:
                console_output(f"Attached to {exe} ({pm.process_id})!")
                return pm

    def hook_dll(self, dll: str):
        """Continually attempt to hook to the given dll under process. Returns MODULEINFO object."""
        module: MODULEINFO = None
        while not module:
            try:
                module = pymem.process.module_from_name(self.p.process_handle, dll)
                if module == None:
                    break
                time.sleep(1)
            except Exception as e:
                console_output(f"{e}")
                break
            else:
                console_output(f"Found {dll} ({hex(module.lpBaseOfDll)})!")
                return module

    def check_hook(self):
        """Check that process (p) is still hooked. Returns True or False."""
        try:
            ret = self.p.base_address # if we can read the process base address, it's still hooked
        except:
            return False
        else:
            return True

    def check_module(self, dll: str):
        """Check that the given module (m) is currently accessible by the process (p). Returns True or False."""
        try:
            m_current: MODULEINFO = pymem.process.module_from_name(self.p.process_handle, dll)
            if m_current == None:
                return False
        except Exception as e:
            console_output(f"{e}")
            return False
        else:
            if self.game_dll == None:
                return False
            if m_current.lpBaseOfDll == self.game_dll.lpBaseOfDll:
                return True
            else:
                return False

    def hooking_loop(self):
        console_output(f"--- HALO 3 RANDOMIZER BY XERO | {datetime.now().strftime('%d%b%Y %H:%M:%S').upper()} ---")
        init_exe: bool = True
        if init_exe:
            init_exe = False
            console_output(f"Waiting for {self.exe_name}...") # Print this string once when we attempt to hook
        while not self.p:
            try:
                self.p = self.hook(self.exe_name)
            except:
                continue
            else:
                break # hook will print "Attached to MCC-Win64-Shipping.exe!"
        
        init_dll: bool = True
        if init_dll:
            init_dll = False
            console_output(f"Waiting for {self.dll_name}...")
        while not self.game_dll:
            try:
                if self.check_hook(): # Ensure we still have process hook, if not this while will break and check_hook loop below will throw back to main()
                    self.game_dll = self.hook_dll("halo3.dll")
                    if self.game_dll == None:
                        raise Exception("Did not find halo3.dll!")
            except:
                continue
            else:
                break # hook_dll will print "Found dll!"


        # Sorry for spaghetti
        has_started_loop: bool = False
        waiting_for_game_msg: bool = True
        in_game_msg: bool = True
        initial_loop: bool = True
        thread_debug_handling = threading.Thread(target=self.start_debug_handling)
        debugger_obj_cpp = None # Define debugger_obj_cpp 
        
        while True:
            # Continually set config values
            config_data['randomize_weapons'] = weapon_randomizer_setting.get()
            config_data['seed'] = seed_setting.get()
            config_data['randomize_seed'] = seed_randomizer_setting.get()

            if self.check_hook() and self.check_module(self.dll_name): # Continually ensure we have a handle on process and DLL

                # continually update current level and bsp
                self.update_current_level()
                self.update_current_bsp()

                if self.current_level in self.ALLOWED_LEVELS: # Check current_level if we're currently on a randomizable level
                    waiting_for_game_msg = True
                    if in_game_msg:
                        console_output(f"Valid level detected ({self.current_level})")
                        in_game_msg = False

                    debugger_obj_cpp = self.cpp_accessor.access_debugger() # Refresh debugger_obj_cpp
                    has_started_loop = True
                    if initial_loop:
                        initial_loop = False
                        random.seed(seed_setting.get() if not seed_randomizer_setting.get() else datetime.now()) # Set the seed based on what user has set in GUI
                        disable_frame(main_window_options_frame) # Prevent user from modifying seed once we begin randomizing
                        self.initial_loop(debugger_obj_cpp, thread_debug_handling) # execute the initial_loop function
                    # main loop
                    self.main_loop(debugger_obj_cpp, thread_debug_handling)


                else: # If we're not in game keep looping until we're back
                    if has_started_loop: # Reset DLL if we already started loop
                        self.p = None
                        self.game_dll = None
                        debugger_obj_cpp.stop()
                        if thread_debug_handling.is_alive():
                            thread_debug_handling.join() # kill the cpp thread since the game is no longer hooked
                        console_output("Not currently in-game, destroying randomizer. Retrying hook in a few seconds...")
                        console_output("NOTE: Restarting the game is recommended due to potential instability.")
                        console_output(f"--- HALO 3 RANDOMIZER TERMINATED | {datetime.now().strftime('%d%b%Y %H:%M:%S').upper()} ---\n")
                        enable_frame(main_window_options_frame) # Allow user to modify seed once we stop randomizing
                        if seed_randomizer_setting.get(): seed_textbox.configure(state="disabled")
                        time.sleep(5) # Wait 5 seconds to try to prevent cases where it will hook again right as app closes
                        self.hooking_loop()
                    if waiting_for_game_msg:
                        console_output("Waiting for valid level...")
                        waiting_for_game_msg = False
                        in_game_msg = True

            else: # If we lost handle on Process or DLL rehook entirely.
                self.p = None
                self.game_dll = None
                if has_started_loop:
                    debugger_obj_cpp.stop()
                    thread_debug_handling.join()
                console_output(f"Lost handle to {self.exe_name} and/or {self.dll_name}. Retrying hook in a few seconds...")
                console_output(f"--- HALO 3 RANDOMIZER TERMINATED | {datetime.now().strftime('%d%b%Y %H:%M:%S').upper()} ---\n")
                seed_textbox.config(state="normal") # Allow user to modify seed once we stop randomizing
                time.sleep(5) # Wait 5 seconds to try to prevent cases where it will hook again right as app closes
                self.hooking_loop()

    def randomize_char(self, ctx): # This needs to be delegated to subclass
        return ctx

    def randomize_char_weapon(self, ctx): # This needs to be delegated to subclass
        return ctx

    def initial_loop(self, debugger_obj_cpp, thread_debug_handling):
        self.set_level = self.current_level

    def main_loop(self, debugger_obj_cpp, thread_debug_handling):
        # Do main loop stuff
        pass


    def start_debug_handling(self):
        randomizer = self.cpp_accessor.access_debugger()
        randomizer.start_handling_breakpoints()

    def generate_character_palette(self):
        pass

    def generate_weapon_palettes(self):
        pass

class Halo3 (Game): # Handle hooking and process stuff
    
    def __init__(self, exe, dll):
        self.cpp_accessor = PyDebugger_CPP
        self.charspawn_offsets = [0x55C2E1] # set character datum @ Rax
        #self.charspawn_offsets = [0x55C2D9] # set character palette index @ Rax
        self.charweapon_offsets = [0x55331F]
        self.curlevel_offsets = [0x1EABB78]
        self.curbsp_offsets = [0xA41D20, 0x2C]
        self.string_dictionary_offsets = [0xA41CF8, 0x820000] # For future reference: obtained by finding serialized string dictionary and finding pointer to the base.
        self.special_offsets = [[0x1C37288],[0xA3F5B8]] # Scenario Mem Pointer, Scenario Tag

        self.ALLOWED_LEVELS = ["010_jungle", "020_base", "030_outskirts", "040_voi", "050_floodvoi", "070_waste", "100_citadel", "110_hc", "120_halo"]

        self.DISQUALIFIED_CHARACTERS = ["marine_johnson", "marine_johnson_halo", "marine_johnson_boss", "dervish", "miranda", "naval_officer", "marine_pilot", "truth", "monitor", "monitor_combat", "brute_phantom", "cortana", "flood_infection", "scarab"]
        self.DISQUALIFIED_WEAPONS = ["primary_skull", "secondary_skull", "monitor_beam", "spartan_laser_overloaded"]

        self.DISQUALIFIED_AREAS = [["020_base", 295]]

        self.DISQUALIFIED_SQUADS =  {
                                        "010_jungle":   [],
                                        "020_base":   [],
                                        "030_outskirts":   [],
                                        "040_voi":   [],
                                        "050_floodvoi":   [],
                                        "070_waste":    [
                                                            0x1CB3ECE8C
                                                        ],
                                        "100_citadel":  [
                                                            0x1CB1BBA80
                                                        ],
                                        
                                        "110_hc":   [],
                                        "120_halo":   []
                                    }

        self.CHARACTER_PALETTE_MODIFICATIONS = { # level_name : { [ [operation, datum | tagstring (removal only)], ... ] } operation is 0 or 1; 0 means remove, 1 means add
            "010_jungle":   [
                                [1, 0x90EB2F59],    # elite
                                [1, 0x911E2F8C],    # elite_major
                                [1, 0x8E622CD0],    # brute_ultra
                            ],
            "020_base":     [
                                [1, 0x96A93518],    # brute_captain_major
                                [1, 0x96AA3519],    # brute_captain_ultra
                                [1, 0x8C9E2B0D],    # brute_major
                                [1, 0x8C9F2B0E],    # brute_ultra
                                [1, 0x974635B5],    # elite
                                [1, 0x977935E8],    # elite_major
                                [1, 0x8E8C2CFB],    # grunt_major
                                [1, 0x8E8D2CFC],    # grunt_ultra
                                [1, 0x914C2FBB],    # jackal_major
                            ],
            "030_outskirts":[
                                [1, 0x92193088],    # brute_captain_major
                                [1, 0x921A3089],    # brute_captain_ultra
                                [1, 0x82FF1A2B],    # brute_ultra
                                [1, 0x93143183],    # bugger_major
                                [1, 0x84EC235B],    # grunt_major
                                [1, 0x84ED235C],    # grunt_ultra
                                [1, 0x8CF22B61],    # jackal_major
                            ],
            "040_voi":      [
                                [1, 0x91BB3044],    # elite
                                [1, 0x92A3312C],    # elite_major
                            ],
            "050_floodvoi": [
                                [0, 'worker'],
                                #[0, 'flood_infection'] # having too many of these crashes the game and/or causes unintended behavior
                            ],
            "070_waste":    [
                            ],
            "100_citadel":  [
                            ],
            "110_hc":       [
                                [1, 0xF92617B0], # elite
                                [1, 0xF92817B2], # elite_major
                            ],
            "120_halo":     [
                                [1, 0x8E952D03], # elite
                                [1, 0x8EC72D35], # elite_major
                            ]
        }

        self.CHARACTER_PALETTE_BSP = {
            "010_jungle":   [
                                [4111, 'jackal'],
                                [4111, 'jackal_major'],
                                [4111, 'jackal_sniper'],
                            ],
            "020_base":     [
                                [291, 'brute'],
                                [291, 'brute_bodyguard'],
                                [291, 'brute_captain'],
                                [291, 'brute_captain_major'],
                                [291, 'brute_captain_ultra'],
                                [291, 'brute_chieftain_armor'],
                                [291, 'brute_chieftain_weapon'],
                                [291, 'brute_jumppack'],
                                [291, 'brute_major'],
                                [291, 'brute_ultra'],
                                [291, 'grunt'],
                                [291, 'grunt_major'],
                                [291, 'grunt_ultra'],
                                [831, 'bugger'],
                                [831, 'bugger_major'],
                            ],
            "030_outskirts":[
                            ],
            "040_voi":      [
                                [271, 'bugger'], # 0x902C2EB5
                                [271, 'bugger_major'], # 0x90772F00
                                [3, 'worker'], # 0x91152F9E
                                [3, 'worker_wounded'], # 0x95F6347F
                                [7, 'elite'], # 0x91BB3044
                                [7, 'elite_major'], # 0x92A3312C
                                [383, 'hunter'], # 0x907E2F07
                                [3, 'jackal'], # 0x825320DC
                                [3, 'jackal_major'], # 0x825520DE
                                [3, 'jackal_sniper'], # 0x910E2F97
                            ],
            "050_floodvoi": [
                                [135, 'flood_carrier'], # 0x82CF2158
                                [159, 'floodcombat_elite'], # 0x842722B0
                                [159, 'flood_pureform_ranged'], # 0x87FE2687
                                [159, 'flood_pureform_stalker'], # 0x884226CB
                                [159, 'flood_pureform_tank'], # 0x8801268A
                            ],
            "070_waste":    [
                                [4099, 'hunter'],
                                [4103, 'sentinel_aggressor'],
                                [4103, 'sentinel_constructor']
                            ],
            "100_citadel":  [
                                [1023, 'hunter'],
                                [49151, 'sentinel_aggressor'],
                                [49151, 'sentinel_aggressor_captain'],
                                [1023, 'bugger'],
                                [-1023, 'bugger'],
                                [1023, 'flood_carrier'],
                                [1023, 'flood_combat_human'],
                                [1023, 'floodcombat_elite'],
                                [1023, 'floodcombat_brute'],
                                [1023, 'flood_pureform_tank'],
                                [1023, 'flood_pureform_stalker'],
                                [1023, 'flood_pureform_ranged'],
                            ],
            "110_hc":       [
                                [163, 'flood_carrier'],
                                [163, 'flood_combat_human'],
                                [163, 'flood_pureform_stalker'],
                                [163, 'flood_pureform_ranged'],
                                [163, 'flood_pureform_tank'],
                            ],
            "120_halo":     [
                                [1151, 'flood_carrier'],
                            ]
        }

        self.WEAPON_PALETTE_MODIFICATIONS = {
            "010_jungle":   [
                                [1, 0xEBCA0A54],    # plasma_cannon
                                [1, 0xF4D3135D],    # smg
                                [1, 0xF600148A],    # excavator
                                [1, 0xF63114BB],    # flak_cannon
                                [1, 0xF8BF1749],    # rocket_launcher
                                [1, 0xF4891313],    # plasma_rifle
                                [1, 0xF86A16F4],    # shotgun
                                [1, 0xECEA0B74],    # machinegun_turret
                            ],
            "020_base":     [
                                [1, 0xF8D91763], # spartan_laser
                                [1, 0xE2BD0147], # machinegun_turret
                                [1, 0x9B5C39CB]  # hunter_particle_cannon
                            ],
            "030_outskirts":[
                                [1, 0xF36511EF], # machinegun_turret
                                [0, 'needler']   # needler doesn't show up for some reason
                            ],
            "040_voi":      [
                                [0, 'missile_pod'],            
                                [0, 'plasma_cannon_undeployed'],
                                [1, 0x90DD2F66], # hunter_particle_cannon
                                [1, 0x94BA3343], # energy_blade
                            ],
            "050_floodvoi": [
                                [1, 0x90752EFE], # excavator
                                [1, 0x8F412DCA], # needler
                                [1, 0x8FB42E3D], # plasma_pistol
                                [1, 0x90312EBA], # beam_rifle
                                [1, 0x8AAD2936], # sniper_rifle
                                [1, 0x8B11299A], # rocket_launcher
                                [1, 0xEFFE0E88], # machinegun_turret
                                [1, 0x887F2708], # flood_ranged_weapon
                            ],
            "070_waste":    [
                                [1, 0x8D7C2C05], # hunter_particle_cannon
                            ],
            "100_citadel":  [
                                [0, 'plasma_cannon_undeployed'],
                                [1, 0x889D2726], # hunter_particle_cannon
                                [1, 0x972C35B5], # flood_ranged_weapon
                                [1, 0x925330DC], # sentinel_gun
                            ],
            "110_hc":       [
                                [1, 0xF7DC1666], # flood_ranged_weapon
                                [1, 0xFF241DAE], # sniper_rifle
                                [1, 0xE7C1064B], # machinegun_turret
                            ],
            "120_halo":     [
                                [1, 0x87BB2629], # sentinel_gun
                                [1, 0x876A25D8], # flood_ranged_weapon
                            ]

        }

        self.WEAPON_PALETTE_BSP = {
            "010_jungle":   [
                                [5631, 'sniper_rifle'],
                                [5631, 'rocket_launcher'],
                                [5631, 'shotgun'],
                            ],
            "020_base":     [
                                [831, 'gravity_hammer'],
                                [1023, 'beam_rifle'],
                                [1023, 'flak_cannon'],
                            ],
            "030_outskirts":[
                                [15, 'spike_rifle'],
                                [15, 'flak_cannon'],
                                [31, 'brute_shot']
                            ],
            "040_voi":      [
                                [383, 'hunter_particle_cannon'],
                                [7, 'energy_blade'],
                                [383, 'shotgun'],
                                [3, 'needler'],
                                [3, 'spike_rifle'],
                                [7, 'brute_shot'],
                                [7, 'sniper_rifle'],
                                [7, 'plasma_cannon'],
                                [383, 'gravity_hammer'],
                                [383, 'shotgun'],
                            ],
            "050_floodvoi": [
                                [135, 'flamethrower'],
                                [159, 'plasma_cannon'],
                                [191, 'machinegun_turret'],
                            ],
            "070_waste":    [
                            ],
            "100_citadel":  [
                                [831, 'plasma_cannon'],
                                [31, 'gravity_hammer'],
                                [1023, 'energy_blade'],
                                [1023, 'rocket_launcher'],
                            ],
            "110_hc":       [
                                [163, 'sniper_rifle'],
                                [163, 'machinegun_turret'],
                            ],
            "120_halo":     [
                            ]
        }

        self.WEAPON_CLASSES = { # "archetype": [[list_regular],[list_valid_randoms]]
            "grunt":    [["plasma_pistol", "needler"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "brute_shot", "plasma_cannon"]],

            "grunt_h":  [["plasma_pistol", "needler", "spike_rifle", "flak_cannon"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "brute_shot", "plasma_cannon"]],

            "jackal":   [["plasma_pistol", "needler"], 
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "beam_rifle", "plasma_rifle", "sniper_rifle"]],

            "jackal_s": [["covenant_carbine", "beam_rifle"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "beam_rifle", "sniper_rifle"]],

            "brute":    [["spike_rifle", "excavator", "covenant_carbine", "plasma_rifle", "brute_shot"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "plasma_rifle", "shotgun", "plasma_cannon", "machinegun_turret", "sentinel_gun", "sniper_rifle"]],

            "brute_hc": [["gravity_hammer"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "plasma_rifle", "shotgun", "sentinel_gun", "sniper_rifle"]],
            
            "brute_cc": [["flak_cannon", "plasma_cannon"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "plasma_rifle", "shotgun", "plasma_cannon", "machinegun_turret", "sentinel_gun", "sniper_rifle"]],

            "bugger":    [["plasma_pistol", "needler"],
                         ["plasma_pistol", "needler", "magnum", "spike_rifle", "smg", "excavator", "plasma_rifle", "assault_rifle", "battle_rifle"]],

            "hunter":    [["hunter_particle_cannon"],
                         ["hunter_particle_cannon"]],

            "elite":    [["needler", "plasma_rifle", "covenant_carbine", "flak_cannon", "energy_blade", "beam_rifle", "spartan_laser", "flamethrower"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "energy_blade", "sniper_rifle", "beam_rifle", "shotgun", "spartan_laser", "plasma_cannon", "machinegun_turret", "flamethrower"]],

            "marine":   [["magnum", "assault_rifle", "battle_rifle", "smg", "rocket_launcher", "shotgun", "spartan_laser", "sniper_rifle"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "sniper_rifle", "flak_cannon", "rocket_launcher", "spartan_laser"]],
            
            "civilian": [["magnum", "null"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "assault_rifle", "smg", "excavator", "sniper_rifle", "flak_cannon", "rocket_launcher", "spartan_laser"]],

            "flood":    [["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "sniper_rifle", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "plasma_rifle", "shotgun", "flamethrower", "gravity_hammer", "null"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spike_rifle", "covenant_carbine", "sniper_rifle", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "plasma_rifle", "shotgun", "flamethrower", "gravity_hammer", "null"]],
            
            "flood_pureranged": [["flood_ranged_weapon"],["flood_ranged_weapon"]],

            "sentinel": [["sentinel_gun"],["sentinel_gun"]],

            "noweapon": [["null"],["null"]]
        }
        self.WEAPON_CLASSES_MAPPING = {
            "brute":                    "brute",
            "brute_bodyguard":          "brute",
            "brute_captain":            "brute",
            "brute_captain_major":      "brute",
            "brute_captain_ultra":      "brute",
            "brute_chieftain_armor":    "brute_hc",
            "brute_chieftain_weapon":   "brute_cc",
            "brute_jumppack":           "brute",
            "brute_major":              "brute",
            "brute_stalker":            "brute",
            "brute_ultra":              "brute",
            "brute_captain_no_grenade": "brute",
            "brute_captain_major_no_grenade": "brute",
            "brute_chieftain_armor_no_grenade": "brute_hc",
            "brute_bodyguard_no_grenade": "brute",

            "worker":                   "civilian",
            "worker_wounded":           "civilian",

            "bugger":                   "bugger",
            "bugger_major":             "bugger",

            "dervish":                  "elite",

            "elite":                    "elite",
            "elite_major":              "elite",
            "elite_specops":            "elite",
            "elite_specops_commander":  "elite",

            "flood_carrier":            "noweapon",
            #"floodcombat_base":         "flood",
            "floodcombat_brute":        "flood",
            "floodcombat_elite":        "flood",
          "floodcombat_elite_shielded": "flood",
            "flood_combat_human":       "flood",
            
            "flood_infection":          "noweapon",

            "flood_pureform_ranged":    "flood_pureranged",
            "flood_pureform_stalker":   "noweapon",
            "flood_pureform_tank":      "noweapon",

            "grunt":                    "grunt",
            "grunt_heavy":              "grunt_h",
            "grunt_major":              "grunt",
            "grunt_ultra":              "grunt",

            "hunter":                   "hunter",

            "jackal":                   "jackal",
            "jackal_major":             "jackal",
            "jackal_sniper":            "jackal_s",

            "marine":                   "marine",
            "marine_female":            "marine",
            "marine_johnson":           "marine",
            "marine_odst":              "marine",
            "marine_odst_sgt":          "marine",
            "marine_no_trade_weapon":   "marine",
            "marine_sgt":               "marine",
            "marine_wounded":           "marine",

            "sentinel_aggressor":       "sentinel",
          "sentinel_aggressor_captain": "sentinel",
            "sentinel_aggressor_major": "sentinel",
            "sentinel_constructor":     "noweapon",
        }

        super().__init__(exe, dll)

    def get_master_character_palette(self, address): # Creates character palette object with the default values for the current level
        cur_index = 0
        palette = Palette(self.current_level, [])

        while (self.p.read_string(address + (cur_index * 16), 4) == "rahc"): # read all character datums from the character palette address
            datum = bytearray(self.p.read_bytes((address + (cur_index * 16) + 12), 4)) # read the four bytes
            datum.reverse() # they are stored in little endian so we want to reverse the byte array
            out = int(f"0x{datum.hex().upper()}", 16)

            if self.get_tag_string(out) not in self.DISQUALIFIED_CHARACTERS:
                palette.add(out) # add this datum to the palette if we haven't disqualified the tag string corresponding to the datum

            cur_index += 1
        
        if self.current_level in self.CHARACTER_PALETTE_MODIFICATIONS:
            for op in self.CHARACTER_PALETTE_MODIFICATIONS[self.current_level]: # Handle palette modifications
                if op[0] == 0: # op[0] == 0 means we want to delete the op[1] from the palette
                    for val in palette.values:
                        if self.get_tag_string(val) == op[1]:
                            try:
                                palette.remove(val)
                            except Exception as e:
                                console_output(e)
                else: # op[0] == 1 means we want to add the op[1] to the palette
                    palette.add(op[1])

        return palette

    def get_master_weapon_palette(self, address): # Creates weapon palette object with the default values for the current level
        cur_index = 0
        palette = Palette(self.current_level, [])

        palette.add(0x00000000) # noweapon choice added for posterity

        while (self.p.read_string(address + (cur_index * 48), 4) == "paew"): # read all weapon datums from the weapon palette address
            datum = bytearray(self.p.read_bytes((address + (cur_index * 48) + 12), 4)) # read the four bytes
            datum.reverse() # stored in little endian so we reverse byte array
            out = int(f"0x{datum.hex().upper()}", 16)

            if self.get_tag_string(out) not in self.DISQUALIFIED_WEAPONS:
                palette.add(out)

            cur_index += 1

        if self.current_level in self.WEAPON_PALETTE_MODIFICATIONS:
            for op in self.WEAPON_PALETTE_MODIFICATIONS[self.current_level]: # Handle palette modifications
                if op[0] == 0:
                    for val in palette.values:
                        if self.get_tag_string(val) == op[1]:
                            try:
                                palette.remove(val)
                            except Exception as e:
                                console_output(e)
                else:
                    palette.add(op[1])

        return palette

    def check_character_palette_bsp(self, datum): # Returns boolean for whether or not the datum is allowed to be randomized in the current bsp
        tag = self.get_tag_string(datum)
        for val in self.CHARACTER_PALETTE_BSP[self.current_level]:
            if val[1] == tag: # If the tag has a condition
                if val[0] > self.current_bsp and val[0] >= 0: # If the designated BSP is higher than the current BSP return False
                    return False
                elif abs(val[0]) < self.current_bsp and val[0] < 0: # If the designated BSP is at or lower than the current BSP return False (if BSP is negative, intended to prevent randos AFTER a bsp)
                    return False
        return True # Return True if we loop through the whole thing and don't find the thing

    def check_weapon_palette_bsp(self, datum): # Returns boolean for whether or not the datum is allowed in the current bsp
        tag = self.get_tag_string(datum)
        for val in self.WEAPON_PALETTE_BSP[self.current_level]:
            if val[1] == tag: # If the tag has a condition
                if val[0] > self.current_bsp: # If the designated BSP is higher than the current BSP return False
                    return False
                if abs(val[0]) <= self.current_bsp and val[0] < 0: # If the designated BSP is at or lower than the current BSP return False (if BSP is negative, intended to prevent randos AFTER a bsp)
                    return False
        return True # Return True if we loop through the whole thing and don't find the thing


    def randomize_char(self, ctx): # Rax = Character Datum, Rbx/R15 = Squad Unit Index, R8 = Character Palette, R10 = Scenario Pointer, R9/R14 = Base Squad Offset relative to R10
        hashed_savevalue = str([ctx['R14'] - ctx['R10'], ctx['Rbx']])

        if hashed_savevalue in self.known_character_randomizations: # if we already randomized in this session, just return the saved randomization to keep seed integrity
            ctx['Rax'] = self.known_character_randomizations[hashed_savevalue]
            return

        level = self.current_level
        
        if ctx['R14'] - ctx['R10'] in self.DISQUALIFIED_SQUADS[level]: # If Base Squad offset is in DISQUALIFIED_SQUADS, don't randomize
            return

        for area in self.DISQUALIFIED_AREAS: # make sure we haven't disqualified the current area, otherwise return non-randomized
            if area[0] == self.current_level and area[1] == self.current_bsp:
                return
            

        palette = self.master_character_palette
        if palette.level != level: # ensure the character palette we have corresponds to the current level
            return

        if not self.check_character_palette_bsp(ctx['Rax']): # if the guy shouldn't be randomized don't do it
            return

        if ctx['Rax'] in palette.values: # Only randomize if the original character datum is in the palette
            rng = random.choice(palette.values)

            while not self.check_character_palette_bsp(rng):
                rng = random.choice(palette.values) # Select a random value from the CharacterPalette that is allowed in current bsp
            
            ctx['Rax'] = rng # set Rax register to the rng value
            msg = f"Character: {self.get_tag_string(rng)}({rng})"
            print(msg)
            logging.info(msg)

            self.known_character_randomizations[hashed_savevalue] = ctx['Rax']

    # Randomize/set weapons
    def randomize_char_weapon(self, ctx): # Rbx = Character Datum for Comparison (Setting does weird things), R8 = Weapon Datum, R9 = UID, R11 = Base Squad

        # if we already "know" this randomization, just set what we know and return
        if ctx['R9'] in self.known_weapon_randomizations:
            ctx['R8'] = self.known_weapon_randomizations[ctx['R9']]
            return

        character = ctx['Rbx'] # Get the character datum
        level = self.current_level
        
        try:
            weapon_palette = self.weapon_palettes[character]
        except: # If there is no weapon_palette, we don't want to randomize this character's weapons.
            return

        if weapon_palette.level != level:
            return

        rng = random.choice(weapon_palette.values)

        while not self.check_weapon_palette_bsp(rng):
            rng = random.choice(weapon_palette.values)

        ctx['R8'] = rng
        msg = f"Weapon: {self.get_tag_string(rng)}({rng})"
        print(msg)
        logging.info(msg)

        self.known_weapon_randomizations[ctx['R9']] = ctx['R8']

    def initial_loop(self, debugger_obj_cpp, thread_debug_handling):
        super().initial_loop(debugger_obj_cpp, thread_debug_handling)

        self.cpp_accessor.create_debugger(self.p.process_id)
        console_output(f"Created randomizer! Seed: {seed_setting.get() if not seed_randomizer_setting.get() else 'R A N D O M I Z E D'}")
        spawn_breakpoint = self.cpp_accessor.Breakpoint(self.get_pointer(self.game_dll, self.charspawn_offsets), self.randomize_char)
        debugger_obj_cpp.create_hardware_breakpoint(0, spawn_breakpoint) # Set hardware breakpoint at H3Randomizer.breakpoints[0] in Dr0 register
        console_output("Set character spawn breakpoint!")
        weapon_randomizer_breakpoint = self.cpp_accessor.Breakpoint(self.get_pointer(self.game_dll, self.charweapon_offsets), self.randomize_char_weapon)
        debugger_obj_cpp.create_hardware_breakpoint(1, weapon_randomizer_breakpoint) # Set hardware breakpoint at H3Randomizer.breakpoints[1] in Dr0 register
        console_output("Set character spawn weapon breakpoint!")
        thread_debug_handling.start()

        self.p.write_bytes(self.get_pointer(self.game_dll, [0x569092]), b'\x90\x90\x90\x90\x90\x90', 6) # enter_vehicle_immediate workaround
        self.p.write_bytes(self.get_pointer(self.game_dll, [0x39980C]), b'\x90\x90', 2) # vehicle_load_magic workaround
        
        self.unlock_all_zonesets()
        self.generate_character_palette()
        self.generate_weapon_palettes()

    def main_loop(self, debugger_obj_cpp, thread_debug_handling):
        super().main_loop(debugger_obj_cpp, thread_debug_handling)

        if self.current_level != self.set_level:
            console_output("New level detected, getting new character and weapon palettes!")
            self.unlock_all_zonesets()
            self.generate_character_palette()
            self.generate_weapon_palettes()
            self.set_level = self.current_level

    def unlock_all_zonesets(self):
        while True:
            try:
                table_offset_pointer = self.get_pointer(self.game_dll, self.special_offsets[1] + [0x54])
                table_offset = self.p.read_ulong(table_offset_pointer + 4) * 4
                base_pointer = self.p.read_ulonglong(self.get_pointer(self.game_dll, self.special_offsets[0]))
            except:
                continue
            else:
                break
        zoneset_count = self.p.read_int(table_offset_pointer)
        zoneset_base = table_offset + base_pointer # Address of "Zone Sets" element 0; each element is 36 bytes long.
        
        for i in range(zoneset_count):
            zoneset = zoneset_base + (36 * i)
            self.p.write_bytes(zoneset + 16, b'\xFF\xFF\xFF\xFF\x00\x00\x00\x00', 8) # Write FF FF FF FF 00 00 00 00 to zoneset + 0x10 (loads all zonesets and removes unloaded)


    def generate_character_palette(self):
        while True:
            try:
                self.master_character_palette = None
                table_offset_pointer = self.get_pointer(self.game_dll, self.special_offsets[1] + [0x3B4])
                table_offset = self.p.read_ulong(table_offset_pointer) * 4
                base_pointer = self.p.read_ulonglong(self.get_pointer(self.game_dll, self.special_offsets[0]))
            except:
                continue
            else:
                break
        
        self.master_character_palette = self.get_master_character_palette(base_pointer + table_offset)

    def generate_weapon_palettes(self):
        while True:
            try:
                self.master_weapon_palette = None
                table_offset_pointer = self.get_pointer(self.game_dll, self.special_offsets[1] + [0x12C])
                table_offset = self.p.read_ulong(table_offset_pointer) * 4
                base_pointer = self.p.read_ulonglong(self.get_pointer(self.game_dll, self.special_offsets[0]))
            except:
                continue
            else:
                break

        self.master_weapon_palette = self.get_master_weapon_palette(base_pointer + table_offset)
        # Reset the weapon_palettes dictionary for the new level
        self.weapon_palettes.clear()

        # Create Palette objects for each character and add to weapon_palettes - this was originally done on each iteration of randomize_char_weapon but that's not efficient
        for character in self.master_character_palette.values:
            try:
                character_weapon_class = self.WEAPON_CLASSES_MAPPING[self.get_tag_string(character)]
            except: # If the character isn't in WEAPON_CLASSES_MAPPING, don't create a palette for it 
                continue

            if weapon_randomizer_setting.get() == 0: # Select the appropriate allowed_weapons to cross with the weapons in the level for the final weapon palette
                allowed_weapons = self.WEAPON_CLASSES[character_weapon_class][0]
            else:
                allowed_weapons = self.WEAPON_CLASSES[character_weapon_class][1]

            values = []

            for weapon in self.master_weapon_palette.values:
                if self.get_tag_string(weapon) in allowed_weapons:
                    values.append(weapon)

            character_weapon_palette = Palette(self.current_level, values)
                    
            if character_weapon_class == "noweapon":
                character_weapon_palette = Palette(self.current_level, [0])

            # Add this character weapon palette to the weapon_palettes dictionary with the character datum as a key
            self.weapon_palettes[character] = character_weapon_palette

g_current_randomizer: Game