import random
import time
from datetime import datetime
import threading
import pymem.process
from pymem import Pymem
import pymem.exception
from pymem.ressources.structure import MODULEINFO

import H3Randomizer_CPP
from mainwindow import *

class Game: # Abstraction for potential future randomizers
    p: Pymem = None
    base_mod: MODULEINFO = None
    game_dll: MODULEINFO = None
    exe_name: str = ""
    dll_name: str = ""
    cpp_accessor = None
    
    current_level: str = None
    current_bsp: int = 0

    character_palette = ["", []] # Indexed at first randomize_char event per level. Structure is [level, [palette_offsets]]

    # TODO: Make these json and autoupdate
    charspawn_offsets = []
    charweapon_offsets = []
    curlevel_offsets = []
    curbsp_offsets = []
    string_dictionary_offsets = []
    special_offsets = [] # Multiple special offsets that are game-specific
    
    seed = 0 # this way we don't lose the original seed value for when game restarts or whatever

    ALLOWED_CHARACTERS = {} # Allowed character datum values
    ALLOWED_WEAPONS = {}
    ALLOWED_WEAPONS_BY_CHARACTER = {}

    known_randomizations = [] # Randomizations that have already occured in this randomizer; ie. do not reroll when restart mission or revert checkpoint. [[SQ, SQ_IDX], SAVED]
    known_weapon_randomizations = [] # Weapon randomizations that have already occured in this randomizer; [[SQ, UID], SAVED]


    def __init__(self, exe, dll):
        self.exe_name = exe
        self.dll_name = dll
        self.hooking_loop()
    
    def get_tag_string(self, datum, only_last: bool = True) -> str:    
        '''
        Returns the string of a given tag datum.
        '''
        i = datum % 0x10000     # Get the lower 4 bits of the tag datum
        i *= 8                  # Multiply by 8 (length of each string table entry)
        dict_base = self.get_pointer(self.game_dll, self.string_dictionary_offsets)
        ptr = self.p.read_ulonglong(dict_base + i)
        
        out = self.p.read_string(ptr, 255)

        if only_last:
            return out.split("\\")[-1]

        return out # Read until string terminator or 255 bytes

    def get_pointer(self, module: MODULEINFO, offsets: list = [0]):
        '''
        Returns a pointer given a module (DLL) and list of offsets.
        '''
        base_offset = 0

        base_offset: int = 0 # Initialize as 0 just in case
        if len(offsets) <= 1:
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
        pointer = self.get_pointer(self.game_dll, self.curlevel_offsets)
        try:
            curlevel = self.p.read_string(pointer, 16)
            self.current_level = curlevel
            return curlevel
        except:
            pass
        
    def update_current_bsp(self): # Potential todo: change this to zones for more accuracy
        '''
        Updates the current bsp variable.
        '''
        pointer = self.get_pointer(self.game_dll, self.curbsp_offsets)
        try:
            curbsp = self.p.read_int(pointer)
            self.current_bsp = curbsp
            return curbsp
        except:
            pass

    def hook(self, exe: str):
        """Continually attempt to get a handle of the defined process (exe). Returns Pymem object."""
        while not self.p: # Continually try to instantiate a new Pymem from the given exe name.
            try:
                pm = Pymem(exe)
                time.sleep(1)
            except Exception as e:
                if isinstance(e, pymem.exception.ProcessNotFound):
                    continue
                elif isinstance(e, pymem.exception.CouldNotOpenProcess):
                    console_output(f"Failed to attach to {exe}.")
                    break
                else:
                    console_output(f"{e}")
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
            ret = self.p.base_address
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
        randomizer_obj_cpp = None # Define randomizer_obj_cpp 
        
        while True:
            if self.check_hook() and self.check_module(self.dll_name): # Continually ensure we have a handle on process and DLL

                self.update_current_level()
                self.update_current_bsp()
                if self.current_level in self.ALLOWED_CHARACTERS.keys(): # Check current_level if we're currently on a randomizable level
                    waiting_for_game_msg = True
                    if in_game_msg:
                        console_output(f"Valid level detected ({self.current_level})")
                        in_game_msg = False
                    randomizer_obj_cpp = self.cpp_accessor.access_randomizer() # Refresh randomizer_obj_cpp
                    has_started_loop = True
                    if initial_loop:
                        initial_loop = False
                        random.seed(seed_setting.get()) # Set the seed based on what user has set in GUI
                        disable_frame(main_window_options_frame) # Prevent user from modifying seed once we begin randomizing
                        self.initial_loop(randomizer_obj_cpp, thread_debug_handling)
                    else:

                        # Main Loop
                        self.main_loop(randomizer_obj_cpp, thread_debug_handling) 


                else: # If we're not in game keep looping until we're back
                    if has_started_loop: # Reset DLL if we already started loop
                        self.p = None
                        self.game_dll = None
                        randomizer_obj_cpp.stop()
                        if thread_debug_handling.is_alive():
                            thread_debug_handling.join()
                        console_output("Not currently in-game, destroying randomizer. Retrying hook in a few seconds...")
                        console_output("NOTE: Restarting the game is recommended due to potential instability.")
                        console_output(f"--- HALO 3 RANDOMIZER TERMINATED | {datetime.now().strftime('%d%b%Y %H:%M:%S').upper()} ---\n")
                        enable_frame(main_window_options_frame) # Allow user to modify seed once we stop randomizing
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
                    randomizer_obj_cpp.stop()
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

    def initial_loop(self, randomizer_obj_cpp, thread_debug_handling):
        # Set config values
        config_data['randomize_weapons'] = weapon_randomizer_setting.get()
        config_data['seed'] = seed_setting.get()

        self.cpp_accessor.create_randomizer(self.p.process_id)
        console_output(f"Created randomizer! Seed: {seed_setting.get()}")
        spawn_breakpoint = self.cpp_accessor.Breakpoint(self.get_pointer(self.game_dll, self.charspawn_offsets), self.randomize_char)
        randomizer_obj_cpp.set_breakpoint(0, spawn_breakpoint) # Set breakpoint a H3Randomizer.breakpoints[0] in Dr0 register
        console_output("Set character spawn breakpoint!")
        weapon_randomizer_breakpoint = self.cpp_accessor.Breakpoint(self.get_pointer(self.game_dll, self.charweapon_offsets), self.randomize_char_weapon)
        randomizer_obj_cpp.set_breakpoint(1, weapon_randomizer_breakpoint) # Set breakpoint a H3Randomizer.breakpoints[0] in Dr0 register
        console_output("Set character spawn weapon breakpoint!")
        thread_debug_handling.start()

    def main_loop(self, randomizer_obj_cpp, thread_debug_handling):
        # Do main loop stuff
        pass


    def start_debug_handling(self):
        randomizer = self.cpp_accessor.access_randomizer()
        randomizer.start_handling_breakpoints()

class Halo3 (Game): # Handle hooking and process stuff
    
    def __init__(self, exe, dll):
        self.cpp_accessor = H3Randomizer_CPP
        self.charspawn_offsets = [0x55C2E1]
        self.charweapon_offsets = [0x55331F]
        self.curlevel_offsets = [0x1EABB78]
        self.curbsp_offsets = [0xA41D20, 0x2C]
        self.string_dictionary_offsets = [0xA41CF8, 0x820000] # For future reference: obtained by finding serialized string dictionary and finding pointer to the base.
        self.special_offsets = [[0x1C37288],[0xA3F5B8]] # Scenario Mem Pointer, Mem Pointer Table


        self.ALLOWED_CHARACTERS = { # level_name : { character_datum : [weapon_class, bsp_instantiated] }
            "010_jungle": {
                            0x8DA22C10: ["brute", 0],     # brute
                            0x93ED325B: ["brute", 0],     # brute_bodyguard
                            0x8DA12C0F: ["brute", 0],     # brute_captain
                            0x904E2EBC: ["brute", 0],     # brute_captain_major
                            0x904F2EBD: ["brute", 0],     # brute_captain_ultra
                            0x90522EC0: ["brute_hc", 0],  # brute_chieftain_armor
                            0x8E612CCF: ["brute", 0],     # brute_major
                            0x8E622CD0: ["brute", 0],     # brute_ultra
                            
                            # 0x90EA2F58: ["elite", 0],     # dervish

                            0x90EB2F59: ["elite", 0],     # elite
                            0x911E2F8C: ["elite", 0],     # elite_major

                            0x87AA2618: ["grunt", 0],     # grunt
                            0x8AC82936: ["grunt_h", 0],   # grunt_heavy
                            0x87A92617: ["grunt", 0],     # grunt_major
                            0x8AC72935: ["grunt", 0],     # grunt_ultra

                            0x8AC92937: ["jackal", 4127],    # jackal
                            0x8B072975: ["jackal", 4127],    # jackal_major
                            0x93EA3258: ["jackal_s", 4127],  # jackal_sniper

                            0xFE6F146E: ["marine", 0],    # marine
                            0x84992307: ["marine", 0],    # marine_female
                            # 0x8D1D2B8B: ["marine", 0],    # marine_johnson
                            0x8B31299F: ["marine", 0],    # marine_sgt
                          },
            "020_base":   {
                            0x8BE92A58: ["brute", 291],     # brute
                            0x9AF33962: ["brute", 291],     # brute_bodyguard
                            0x96A73516: ["brute", 291],     # brute_captain
                            0x96A93518: ["brute", 291],     # brute_captain_major
                            0x96AA3519: ["brute", 291],     # brute_captain_ultra
                            0x974335B2: ["brute_hc", 291],    # brute_chieftain_armor
                            0x96AB351A: ["brute_cc", 291],    # brute_chieftain_weapon
                            0x91862FF5: ["brute", 291],       # brute_jumppack
                            0x8C9E2B0D: ["brute", 291],       # brute_major
                            0x8C9F2B0E: ["brute", 291],       # brute_ultra
                            # 0x91762FE5: ["drone", 0],       # bugger
                            # 0x91852FF4: ["brute", 0],       # bugger_major
                            # 0x974535B4: ["elite", 0],       # dervish
                            0x974635B5: ["elite", 0],       # elite
                            0x977935E8: ["elite", 0],       # elite_major
                            0x8E8A2CF9: ["grunt", 291],       # grunt
                            0x8E8C2CFB: ["grunt", 291],       # grunt_major
                            0x8E8D2CFC: ["grunt", 291],       # grunt_ultra
                            # 0x9AF73966: ["hunter", 0],      # hunter
                            0x910F2F7E: ["jackal", 0],      # jackal
                            0x914C2FBB: ["jackal", 0],      # jackal_major
                            0x9A4538B4: ["jackal_s", 0],    # jackal_sniper
                            # 0x86A21968: ["marine", 0],      # marine
                            0x93AB321A: ["marine", 0],      # marine_female
                            # 0x9B8C39FB: ["marine", 0],      # marine_pilot
                            0x91BF302E: ["marine", 0],      # marine_sgt
                            0x8BE72A56: ["marine", 0],      # marine_wounded
                            # 0x9ACB393A: ["marine", 0],      # naval_officer
                            # 0x9A4738B6: ["marine", 0],      # miranda
                            # 0x9AF53964: ["grunt", 0],       # truth
                          },
            "030_outskirts": {
                            0x82FC1A28: "brute",     # brute
                            0x84EA2359: "grunt",     # grunt
                            0x876F25DE: "marine",    # marine
                            0x8CB52B24: "jackal",    # jackal
                            0x82FE1A2A: "brute",     # brute_major
                            0x8D1D2B8C: "marine",    # marine_female
                            0x902B2E9A: "marine",    # marine_sgt
                            0x92173086: "brute",     # brute_captain
                            0x921B308A: "grunt_h",   # grunt_heavy
                            0x921C308B: "jackal_s",  # jackal_sniper
                            0x921E308D: "brute",     # brute_jumppack
                            0x922E309D: "brute_cc",  # brute_chieftain_weapon
                            0x92C63135: "drone",     # bugger
            }
        }
        self.ALLOWED_WEAPONS = { # level_name : { weapon : [weapon_datum, bsp_instantiated] }
            "010_jungle": {
                            "plasma_cannon":   [0xEBCA0A54, 0], # Plasma Cannon
                            "battle_rifle":    [0xEEC60D50, 0], # BR
                            "plasma_pistol":   [0xEF260DB0, 0], # PP
                            "needler":         [0xEFFD0E87, 0], # Needler
                            "magnum":          [0xE5E0046A, 0], # Magnum
                            "spiker":          [0xF07B0F05, 0], # Spiker
                            "brute_shot":      [0xF17A1004, 0], # Brute Shot
                            "carbine":         [0xF17A1004, 0], # Carbine
                            "gravity_hammer":  [0xF1C91053, 0], # Gravity Hammer
                            "beam_rifle":      [0xF1E81075, 0], # Beam Rifle
                            "sniper_rifle":    [0xF23610C0, 5631], # Sniper Rifle only loaded after downed pelican
                            "assault_rifle":   [0xF2991123, 0], # Assault Rifle
                            "energy_sword":    [0xF2D81162, 0], # Energy Sword
                            "smg":             [0xF4D3135D, 0], # SMG
                            "excavator":       [0xF600148A, 0], # Mauler
                            "flak_cannon":     [0xF63114BB, 0], # FRG
                            "rocket_launcher": [0xF8BF1749, 5631], # Rocket Launcher only loaded after downed pelican
                            "plasma_rifle":    [0xF4891313, 0], # Plasma Rifle
                            "shotgun":         [0xF86A16F4, 5631] # Shotgun only loaded after downed pelican 5631, 6143 
                          },
            "020_base": {
                            "plasma_cannon":   [0xF1260FB0, 0], # Plasma Cannon
                            "battle_rifle":    [0xE6C1054B, 0], # BR
                            "plasma_pistol":   [0xF46A12F4, 0], # PP
                            "needler":         [0xF3EB1275, 0], # Needler
                            "magnum":          [0xE9A1082B, 0], # Magnum
                            "spiker":          [0xF39E1228, 0], # Spiker
                            "brute_shot":      [0xF53713C1, 0], # Brute Shot
                            "carbine":         [0xF57513FF, 0], # Carbine
                            "gravity_hammer":  [0xF5C0144A, 831], # Gravity Hammer only after Chieftain
                            "beam_rifle":      [0xF65414DE, 1023], # Beam Rifle only after Hangar 2
                            "assault_rifle":   [0xE5C2044C, 0], # Assault Rifle
                            "energy_sword":    [0xF6EC1576, 0], # Energy Sword
                            "smg":             [0xE8B0073A, 0], # SMG
                            "flak_cannon":     [0xF69D1527, 1023], # FRG
                            "spartan_laser":   [0xF8D91763, 0], # Spartan Laser
                            "plasma_rifle":    [0xF5E2146C, 0], # Plasma Rifle
                            "shotgun":         [0xE72305AD, 0], # Shotgun
                          "machinegun_turret": [0xE2BD0147, 0], # Machine Gun
                          },
            "030_outskirts": {
                            #"magnum":          [0xEA83090D, 0], # Magnum doesn't show up
                            #"needler":         [0xF93917C3, 0], # Needler doesn't show up
                            "plasma_pistol":   [0xF6B0153A, 0], # Plasma Pistol
                            "assault_rifle":   [0xF51A13A4, 0], # Assault Rifle
                            "battle_rifle":    [0xF56F13F9, 0], # Battle Rifle
                            "beam_rifle":      [0xF893171D, 0], # Beam Rifle
                            "carbine":         [0xF7BE1648, 0], # Carbine
                            "plasma_rifle":    [0xF80C1696, 0], # Plasma Rifle
                            "shotgun":         [0xF8E0176A, 0], # Shotgun
                            "sniper_rifle":    [0xF65414DE, 0], # Sniper Rifle
                            "spiker":          [0xF5BB1445, 15], # Spiker
                            "flak_cannon":     [0xF85A16E4, 15], # FRG
                            "brute_shot":      [0xF77F1609, 31], # Brute Shot
                            "plasma_cannon":   [0xF300118A, 0], # Plasma Cannon
                          "machinegun_turret": [0xF36511EF, 0], # Machine Gun
                          }
        }
        self.ALLOWED_WEAPONS_BY_CHARACTER = { # "archetype": [[list_regular],[list_valid_randoms]]
            "grunt":    [["plasma_pistol", "needler"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "brute_shot"]],

            "grunt_h":  [["plasma_pistol", "needler", "spiker", "flak_cannon", "excavator"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "brute_shot"]],

            "jackal":   [["plasma_pistol", "needler"], 
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "beam_rifle", "plasma_rifle"]],

            "jackal_s": [["carbine", "beam_rifle"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "beam_rifle"]],

            "brute":    [["spiker", "excavator", "carbine", "plasma_rifle"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "plasma_rifle", "shotgun"]],

            "brute_hc": [["gravity_hammer"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "plasma_rifle", "shotgun"]],
            
            "brute_cc": [["flak_cannon", "plasma_cannon"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "plasma_rifle", "shotgun", "plasma_cannon", "machinegun_turret"]],

            "drone":    [["plasma_pistol", "needler"],
                         ["plasma_pistol", "needler", "magnum", "spiker", "smg", "excavator", "plasma_rifle"]],

            "hunter":    [["hunter_particle_cannon"],
                         ["hunter_particle_cannon"]],

            "elite":    [["needler", "plasma_pistol", "plasma_rifle", "carbine", "flak_cannon", "energy_sword", "beam_rifle", "spartan_laser"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "energy_sword", "sniper_rifle", "beam_rifle", "shotgun", "spartan_laser", "plasma_cannon"]],

            "marine":   [["magnum", "assault_rifle", "battle_rifle", "smg", "rocket_launcher", "shotgun", "spartan_laser"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "sniper_rifle", "flak_cannon", "rocket_launcher", "spartan_laser"]]
           
        }

        super().__init__(exe, dll)

    def index_character_palette(self, address): # Takes character palette addresses and adds all of the entries to character_palette[1]; Unused for now but confirmed to work
        cur_index = 0
        new_palette = []
        while (self.p.read_string(address + (cur_index * 16), 4) == "rahc"):
            datum = bytearray(self.p.read_bytes((address + (cur_index * 16) + 12), 4))
            datum.reverse()
            new_palette.append(datum)
            cur_index += 1
        self.character_palette[0] = self.current_level
        self.character_palette[1] = new_palette


    def randomize_char(self, ctx): # Rax = Character Palette Index, Rbx/R15 = Squad Unit Index, R8 = Character Palette, R9/R14 = Base Squad Address (not consistent)
        if [ctx['R9'], ctx['Rbx']] not in (i[0] for i in self.known_randomizations):
            #if self.character_palette[0] != self.current_level: # Index character palette for the first time
            #    self.index_character_palette(ctx['R8'])
            rng = -1
            level = self.current_level

            if level in self.ALLOWED_CHARACTERS.keys(): # only randomize if we've defined the level

                allowed = self.ALLOWED_CHARACTERS[level] # Some conversion necessary since ALLOWED_CHARACTERS is a dictionary

                if ctx['Rax'] in (allowed): # Only randomize if the original character datum is in ALLOWED_CHARACTERS
                    while True: # Randomize until we get a character that's allowed in the current BSP
                        rng = random.choice(list(allowed.items())) # Select a random value from ALLOWED_CHARACTERS
                        if rng[1][1] < self.current_bsp:
                            break

                    ctx['Rax'] = rng[0]
                    print(self.get_tag_string(rng[0]))
                    self.known_randomizations.append([[ctx['R9'], ctx['Rbx']], ctx['Rax']])
        else:
            known = [i for i in self.known_randomizations if i[0] == [ctx['R9'], ctx['Rbx']]]
            ctx['Rax'] = known[0][1]

        return ctx # Must return ctx no matter what

    # Randomize/set weapons
    def randomize_char_weapon(self, ctx): # Rbx = Character Datum for Comparison (Setting does weird things), R8 = Weapon Datum, R9 = UID, R11 = Base Squad
        if ctx['R9'] not in (i[0] for i in self.known_weapon_randomizations):
            character = ctx['Rbx'] # Get the character datum
            rng = -1
            choice = [0, 0]
            level = self.current_level
            
            allowed_characters_on_level = self.ALLOWED_CHARACTERS[level]
            allowed_weapons_on_level = self.ALLOWED_WEAPONS[level]

            try:
                character_weapon_class = allowed_characters_on_level[character][0]
            except:
                return ctx
            
            allowed_weapons_normal = self.ALLOWED_WEAPONS_BY_CHARACTER[character_weapon_class][0]
            allowed_weapons_random = self.ALLOWED_WEAPONS_BY_CHARACTER[character_weapon_class][1]

            if weapon_randomizer_setting.get() == 0: # If we only want locked randomized weapons (default for class)
                allowed_weapons = allowed_weapons_normal
            else:
                allowed_weapons = allowed_weapons_random

            while rng not in allowed_weapons_on_level:
                rng = random.choice(allowed_weapons)
                try:
                    choice = allowed_weapons_on_level[rng]
                    if choice[1] > self.current_bsp: # If the choice is after designated BSP
                        rng = -1
                        if len(allowed_weapons) < 2: # if there are no other options, return the map default
                            return ctx
                        continue
                    else:
                        break
                except:
                    continue
            ctx['R8'] = choice[0]
            self.known_weapon_randomizations.append([ctx['R9'], ctx['R8']])
        else:
            known = [i for i in self.known_weapon_randomizations if i[0] == ctx['R9']]
            ctx['R8'] = known[0][1]

        return ctx # Must return ctx no matter what

    def initial_loop(self, randomizer_obj_cpp, thread_debug_handling):
        super().initial_loop(randomizer_obj_cpp, thread_debug_handling)
        self.p.write_bytes(self.get_pointer(self.game_dll, [0x569092]), b'\x90\x90\x90\x90\x90\x90', 6) # enter_vehicle_immediate workaround
        self.p.write_bytes(self.get_pointer(self.game_dll, [0x39980C]), b'\x90\x90', 2) # vehicle_load_magic workaround

        table_offset_pointer = self.get_pointer(self.game_dll, self.special_offsets[1] + [0x3B4])
        table_offset = self.p.read_ulong(table_offset_pointer) * 4
        base_pointer = self.p.read_ulonglong(self.get_pointer(self.game_dll, self.special_offsets[0]))

        val = self.p.read_bytes(base_pointer + table_offset, 272)
        
        print(val)


g_current_randomizer: Game