import random
from sys import dllhandle
import time
from datetime import datetime
import threading
import pymem.process
from pymem import Pymem
from pymem.ptypes import RemotePointer
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

    character_palette = ["", []] # Indexed at first randomize_enemy event per level. Structure is [level, [palette_offsets]]

    # TODO: Make these json and autoupdate
    enemyspawn_offsets = []
    curlevel_offsets = []
    curbsp_offsets = []
    
    seed = 0 # this way we don't lose the original seed value for when game restarts or whatever

    ALLOWED_INDICES = {} # Allowed character palette indices
    ALLOWED_INDICES_BY_CLASS = {} # Character datum mapped to weapon class
    ALLOWED_WEAPON_INDICES = {}
    ALLOWED_WEAPONS_BY_CLASS = {}
    DISQUALIFIED_SQUADS = {} # Squads that should not be randomized

    known_randomizations = [] # Randomizations that have already occured in this randomizer; ie. do not reroll when restart mission or revert checkpoint. [[SQ, SQ_IDX], SAVED]
    known_weapon_randomizations = [] # Weapon randomizations that have already occured in this randomizer; [[SQ, UID], SAVED]


    def __init__(self, exe, dll):
        self.exe_name = exe
        self.dll_name = dll
        self.hooking_loop()

    def get_pointer(self, module: MODULEINFO, offsets: list = [0]):
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
        pointer = self.get_pointer(self.game_dll, self.curlevel_offsets)
        try:
            curlevel = self.p.read_string(pointer, 10)
            self.current_level = curlevel
        except:
            pass
        
    def update_current_bsp(self):
        pointer = self.get_pointer(self.game_dll, self.curbsp_offsets)
        try:
            curbsp = self.p.read_int(pointer)
            self.current_bsp = curbsp
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
                if self.current_level in self.ALLOWED_INDICES.keys(): # Check current_level if we're currently on a randomizable level
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

    def randomize_enemy(self, ctx): # This needs to be delegated to subclass
        return ctx

    def randomize_enemy_weapons(self, ctx): # This needs to be delegated to subclass
        return ctx

    def initial_loop(self, randomizer_obj_cpp, thread_debug_handling):
        # Set config values
        config_data['randomize_weapons'] = weapon_randomizer_setting.get()
        config_data['seed'] = seed_setting.get()

        self.cpp_accessor.create_randomizer(self.p.process_id)
        console_output(f"Created randomizer! Seed: {seed_setting.get()}")
        spawn_breakpoint = self.cpp_accessor.Breakpoint(self.get_pointer(self.game_dll, self.enemyspawn_offsets), self.randomize_enemy)
        randomizer_obj_cpp.set_breakpoint(0, spawn_breakpoint) # Set breakpoint a H3Randomizer.breakpoints[0] in Dr0 register
        console_output("Set enemy spawn breakpoint!")
        weapon_randomizer_breakpoint = self.cpp_accessor.Breakpoint(self.get_pointer(self.game_dll, self.enemyspawn_weapon_offsets), self.randomize_enemy_weapons)
        randomizer_obj_cpp.set_breakpoint(1, weapon_randomizer_breakpoint) # Set breakpoint a H3Randomizer.breakpoints[0] in Dr0 register
        console_output("Set enemy weapon randomizer!")
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
        self.enemyspawn_offsets = [0x55C2D9]
        self.enemyspawn_weapon_offsets = [0x55331F]
        self.curlevel_offsets = [0x1EABB78]
        self.curbsp_offsets = [0xA41D20, 0x2C]

        # Ideally, this stuff won't need to be hard coded once I can get tag strings
        self.ALLOWED_INDICES = {
            "010_jungle": [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 14, 15, 16]
            #"020_base": [2, 3, 4, 5, 6, 9, 10, 11, 13, 17, 19] # TODO: unrandomizable in hangar and drone fight
        }
        self.ALLOWED_INDICES_BY_CLASS = { # level_name : { character_datum : weapon_class }
            "010_jungle": {
                            0xFE6F146E: "marine",    # marine
                            0x84992307: "marine",    # marine_female
                            0x87A92617: "grunt",     # grunt_major
                            0x87AA2618: "grunt",     # grunt
                            0x8AC82936: "grunt_h",   # grunt_heavy
                            0x8AC92937: "jackal",    # jackal
                            0x8B072975: "jackal",    # jackal_major
                            0x8B31299F: "marine",    # marine_sgt
                            0x8AC72935: "grunt",     # grunt_ultra
                            0x8DA02C0E: "brute",     # brute_captain_no_grenade
                            0x90502EBE: "brute",     # brute_captain_major_no_grenade
                            0x90512EBF: "brute_hc",  # brute_chieftain_armor_no_grenade
                            0x93EA3258: "jackal_s",  # jackal_sniper
                            0x93EC325A: "brute",     # brute_bodyguard_no_grenade
                            0x8DA22C10: "brute"      # brute
                          }
        }
        self.ALLOWED_WEAPON_INDICES = { # level_name : { weapon : [weapon_datum, bsp_instantiated] }
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
                          }
        }
        self.ALLOWED_WEAPONS_BY_CLASS = { # "archetype": [[list_regular],[list_valid_randoms]]
            "grunt":    [["plasma_pistol", "needler"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon"]],

            "grunt_h":  [["plasma_pistol", "needler", "spiker", "flak_cannon", "excavator"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon"]],

            "jackal":   [["plasma_pistol", "needler"], 
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "beam_rifle", "plasma_rifle"]],

            "jackal_s": [["carbine", "beam_rifle"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "beam_rifle"]],

            "brute":    [["spiker", "brute_shot", "excavator", "carbine", "flak_cannon", "plasma_rifle"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "plasma_rifle", "shotgun"]],

            "brute_hc": [["gravity_hammer"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "plasma_rifle", "shotgun"]],

            "drone":    [["plasma_pistol", "needler", "plasma_rifle"],
                         ["plasma_pistol", "needler", "magnum", "spiker", "smg", "excavator", "plasma_rifle"]],

            "drone":    [["plasma_pistol", "needler"],
                         ["plasma_pistol", "needler", "magnum", "spiker", "smg", "excavator"]],

            "elite":    [["needler", "plasma_pistol", "plasma_rifle", "carbine", "flak_cannon", "energy_sword", "beam_rifle", "spartan_laser"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "flak_cannon", "rocket_launcher", "gravity_hammer", "energy_sword", "sniper_rifle", "beam_rifle", "shotgun", "spartan_laser", "plasma_cannon"]],

            "marine":   [["magnum", "assault_rifle", "battle_rifle", "smg", "rocket_launcher", "shotgun", "spartan_laser"],
                         ["battle_rifle", "plasma_pistol", "needler", "magnum", "spiker", "carbine", "assault_rifle", "smg", "excavator", "sniper_rifle", "flak_cannon", "rocket_launcher", "spartan_laser"]]
           
        }
        self.DISQUALIFIED_SQUADS = { 
            "010_jungle":   [
                                [0x7FF4F5A065D4, 0],
                                [0x7FF4F5A06B94, 0],
                                [0x7FF4F5A067CC, 0],
                                [0x7FF4F5A06AAC, 0],
                                [0x7FF4F5A0E8BC, 0],
                                [0x7FF4F5A0E8BC, 1],
                                [0x7FF4F5A15EEC, 0],
                                [0x7FF4F5A19C14, 0],
                                [0x7FF4F5A19E0C, 0],
                                [0x7FF4F5A1A004, 0],
                                [0x7FF4F5A1A1FC, 0],
                            ]
            }

        super().__init__(exe, dll)

    def level_maximum_palette_index(self):
          return max(self.ALLOWED_INDICES[self.current_level])

    def get_allowed_palette_indices(self):
        return self.ALLOWED_INDICES[self.current_level]

    def get_allowed_weapon_palette_indices(self):
        return self.ALLOWED_WEAPON_INDICES[self.current_level]

    def index_character_palette(self, address):
        cur_index = 0
        new_palette = []
        while (self.p.read_string(address + (cur_index * 16), 4) == "rahc"):
            datum = bytearray(self.p.read_bytes((address + (cur_index * 16) + 12), 4))
            datum.reverse()
            new_palette.append(datum)
            cur_index += 1
        self.character_palette[0] = self.current_level
        self.character_palette[1] = new_palette


    def randomize_enemy(self, ctx): # Rax = Character Palette Index, Rbx/R15 = Squad Unit Index, R8 = Character Palette, R9/R14 = Base Squad
        if [ctx['R9'], ctx['Rbx']] not in self.DISQUALIFIED_SQUADS[self.current_level]: # Don't randomize if it's a DQ'd index of/or DQ'd squad

            if [ctx['R9'], ctx['Rbx']] not in (i[0] for i in self.known_randomizations):
                if self.character_palette[0] != self.current_level: # Index character palette for the first time
                    self.index_character_palette(ctx['R8'])
                rng = -1
                level = self.current_level
                allowed = self.get_allowed_palette_indices()
                if level in self.ALLOWED_INDICES.keys(): # only randomize if we've defined the level
                    if ctx['Rax'] in allowed: # Only randomize if we allow it
                        rng = random.choice(allowed) # Select a random value from ALLOWED_INDICES
                        ctx['Rax'] = rng
                        self.known_randomizations.append([[ctx['R9'], ctx['Rbx']], ctx['Rax']])
            else:
                known = [i for i in self.known_randomizations if i[0] == [ctx['R9'], ctx['Rbx']]]
                ctx['Rax'] = known[0][1]

        return ctx # Must return ctx no matter what

    # Randomize/set enemy weapons
    def randomize_enemy_weapons(self, ctx): # Rbx = Character Datum for Comparison (Setting does weird things), R8 = Weapon Datum, R9 = UID, R11 = Base Squad
        if ctx['R9'] not in (i[0] for i in self.known_weapon_randomizations):
            character = ctx['Rbx'] # Get the character datum
            rng = -1
            choice = [0, 0]
            level = self.current_level
            
            allowed_indices_by_class = self.ALLOWED_INDICES_BY_CLASS[level]
            allowed_weapon_indices = self.ALLOWED_WEAPON_INDICES[level]

            try:
                allowed = allowed_indices_by_class[character]
            except:
                return ctx
            
            allowed_weapons_by_class_normal = self.ALLOWED_WEAPONS_BY_CLASS[allowed][0]
            allowed_weapons_by_class_random = self.ALLOWED_WEAPONS_BY_CLASS[allowed][1]

            if weapon_randomizer_setting.get() == 0: # If we only want locked randomized weapons (default for class)
                allowed_weapons = allowed_weapons_by_class_normal
            else:
                allowed_weapons = allowed_weapons_by_class_random

            while rng not in allowed_weapon_indices:
                rng = random.choice(allowed_weapons)
                try:
                    choice = allowed_weapon_indices[rng]
                    if choice[1] > self.current_bsp:
                        rng = -1
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

g_current_randomizer: Game