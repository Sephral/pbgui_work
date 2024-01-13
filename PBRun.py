import psutil
import subprocess
import configparser
import shlex
import sys
from pathlib import Path, PurePath
from time import sleep
import glob
import json
from io import TextIOWrapper
from datetime import datetime
import platform
from shutil import copy
import os

class RunInstance():
    def __init__(self):
        self._user = None
        self._symbol = None
        self._parameter = None
        self._path = None
    
    @property
    def user(self): return self._user
    @property
    def symbol(self): return self._symbol
    @property
    def parameter(self): return self._parameter
    @property
    def path(self): return self._path

    @user.setter
    def user(self, new_user):
        if self._user != new_user:
            self._user = new_user
    @symbol.setter
    def symbol(self, new_symbol):
        if self._symbol != new_symbol:
            self._symbol = new_symbol
    @parameter.setter
    def parameter(self, new_parameter):
        if self._parameter != new_parameter:
            self._parameter = new_parameter
    @path.setter
    def path(self, new_path):
        if self._path != new_path:
            self._path = new_path


    def watch(self):
        if not self.is_running():
            self.start()

    def is_running(self):
        if self.pid():
            return True
        return False

    def pid(self):
        for process in psutil.process_iter():
            try:
                cmdline = process.cmdline()
            except psutil.NoSuchProcess:
                pass
            except psutil.AccessDenied:
                pass
            if self.user in cmdline and self.symbol in cmdline and any("passivbot.py" in sub for sub in cmdline):
                return process

    def stop(self):
        if self.is_running():
            print(f'{datetime.now().isoformat(sep=" ", timespec="seconds")} Stop: {self.user} {self.symbol}')
            self.pid().kill()

    def start(self):
        if not self.is_running():
            pb_config = configparser.ConfigParser()
            pb_config.read('pbgui.ini')
            if pb_config.has_option("main", "pbdir"):
                pbdir = pb_config.get("main", "pbdir")
                config = PurePath(f'{self.path}/config.json')
                cmd = [sys.executable, '-u', PurePath(f'{pbdir}/passivbot.py')]
                cmd_end = f'{self.parameter} {self.user} {self.symbol} '.lstrip(' ')
                cmd.extend(shlex.split(cmd_end))
                cmd.extend([config])
                logfile = Path(f'{self.path}/passivbot.log')
                log = open(logfile,"ab")
                if platform.system() == "Windows":
                    creationflags = subprocess.DETACHED_PROCESS
                    creationflags |= subprocess.CREATE_NO_WINDOW
                    subprocess.Popen(cmd, stdout=log, stderr=log, cwd=pbdir, text=True, creationflags=creationflags)
                else:
                    subprocess.Popen(cmd, stdout=log, stderr=log, cwd=pbdir, text=True, start_new_session=True)
                print(f'{datetime.now().isoformat(sep=" ", timespec="seconds")} Start: {cmd_end}')

    def clean_log(self):
        logfile = Path(f'{self.path}/passivbot.log')
        if logfile.exists():
            if logfile.stat().st_size >= 10485760:
                logfile_old = Path(f'{str(logfile)}.old')
                copy(logfile,logfile_old)
                with open(logfile,'r+') as file:
                    file.truncate()

    def load(self):
        file = Path(f'{self.path}/instance.cfg')
        with open(file, "r", encoding='utf-8') as f:
            instance_cfg = json.load(f)
            self.user = instance_cfg["_user"]
            self.symbol = instance_cfg["_symbol"]
            self.parameter = ""
            if instance_cfg["_long_mode"] == "graceful_stop":
                self.parameter = (self.parameter + f' -lm gs').lstrip(' ')
            if instance_cfg["_long_mode"] == "panic":
                self.parameter = (self.parameter + f' -lm p').lstrip(' ')
            if instance_cfg["_long_mode"] == "tp_only":
                self.parameter = (self.parameter + f' -lm t').lstrip(' ')
            if instance_cfg["_short_mode"] == "graceful_stop":
                self.parameter = (self.parameter + f' -sm gs').lstrip(' ')
            if instance_cfg["_short_mode"] == "panic":
                self.parameter = (self.parameter + f' -sm p').lstrip(' ')
            if instance_cfg["_short_mode"] == "tp_only":
                self.parameter = (self.parameter + f' -sm t').lstrip(' ')
            if instance_cfg["_market_type"] != "swap":
                self.parameter = (self.parameter + f' -m spot').lstrip(' ')
            if not instance_cfg["_ohlcv"]:
                self.parameter = (self.parameter + f' -oh n').lstrip(' ')
            if instance_cfg["_co"] != -1:
                self.parameter = (self.parameter + f' -co {instance_cfg["_co"]}').lstrip(' ')
            if instance_cfg["_leverage"] != 7:
                self.parameter = (self.parameter + f' -lev {instance_cfg["_leverage"]}').lstrip(' ')
            if instance_cfg["_assigned_balance"] != 0:
                self.parameter = (self.parameter + f' -ab {instance_cfg["_assigned_balance"]}').lstrip(' ')
            if instance_cfg["_price_distance_threshold"] != 0.5:
                self.parameter = (self.parameter + f' -pt {instance_cfg["_price_distance_threshold"]}').lstrip(' ')
            if instance_cfg["_price_precision"] != 0.0:
                self.parameter = (self.parameter + f' -pp {instance_cfg["_price_precision"]}').lstrip(' ')
            if instance_cfg["_price_step"] != 0.0:
                self.parameter = (self.parameter + f' -ps {instance_cfg["_price_step"]}').lstrip(' ')


class PBRun():
    def __init__(self):
        self.run_instances = []
        self.index = 0
        pbgdir = Path.cwd()
        self.instances_path = f'{pbgdir}/data/instances'
        self.cmd_path = f'{pbgdir}/data/cmd'
        if not Path(self.cmd_path).exists():
            Path(self.cmd_path).mkdir(parents=True)            
        self.piddir = Path(f'{pbgdir}/data/pid')
        if not self.piddir.exists():
            self.piddir.mkdir(parents=True)
        self.pidfile = Path(f'{self.piddir}/pbrun.pid')
        self.my_pid = None

    def __iter__(self):
        return iter(self.run_instances)

    def __next__(self):
        if self.index > len(self.run_instances):
            raise StopIteration
        self.index += 1
        return next(self)

    def add(self, run_instance: RunInstance):
        if run_instance:
            self.run_instances.append(run_instance)

    def remove(self, run_instance: RunInstance):
        if run_instance:
            self.run_instances.remove(run_instance)

    def start_instance(self, instance):
        self.change_enabled(instance, True)
        ipath = f'{self.instances_path}/{instance}'
        self.update(ipath, True)

    def stop_instance(self, instance):
        self.change_enabled(instance, False)
        ipath = f'{self.instances_path}/{instance}'
        self.update(ipath, False)

    def disable_instance(self, instance):
        self.change_enabled(instance, False)

    def enable_instance(self, instance):
        self.change_enabled(instance, True)

    def change_enabled(self, instance : str, enabled : bool):
        ipath = f'{self.instances_path}/{instance}'
        ifile = Path(f'{ipath}/instance.cfg')
        with open(ifile, "r", encoding='utf-8') as f:
            inst = json.load(f)
            inst["_enabled"] = enabled
            f.close()
        with open(ifile, "w", encoding='utf-8') as f:
            json.dump(inst, f, indent=4)

    def restart(self, user : str, symbol : str):
        cfile = Path(f'{self.cmd_path}/restart.cmd')
        cfg = ({
            "user": user,
            "symbol": symbol})
        with open(cfile, "w", encoding='utf-8') as f:
            json.dump(cfg, f)

    def has_restart(self):
        cfile = Path(f'{self.cmd_path}/restart.cmd')
        if cfile.exists():
            with open(cfile, "r", encoding='utf-8') as f:
                cfg = json.load(f)
                for instance in self.run_instances:
                    if instance.user == cfg["user"] and instance.symbol == cfg["symbol"]:
                        instance.stop()
                        instance.load()
                        instance.start()
            cfile.unlink(missing_ok=True)
    
    def update(self, instance_path : str, enabled : bool):
        cfile = Path(f'{self.cmd_path}/update.cmd')
        cfg = ({
            "path": instance_path,
            "enabled": enabled})
        with open(cfile, "w", encoding='utf-8') as f:
            json.dump(cfg, f)

    def has_update(self):
        cfile = Path(f'{self.cmd_path}/update.cmd')
        if cfile.exists():
            with open(cfile, "r", encoding='utf-8') as f:
                cfg = json.load(f)
                if cfg["enabled"]:
                    self.load(cfg["path"])
                else:
                    for instance in self.run_instances:
                        if instance.path == cfg["path"]:
                            instance.stop()
                            self.remove(instance)
            cfile.unlink(missing_ok=True)

    def load(self, instance: str):
        file = Path(f'{instance}/instance.cfg')
        if file.exists():
            with open(file, "r", encoding='utf-8') as f:
                instance_cfg = json.load(f)
                if "_enabled" in instance_cfg:
                    if instance_cfg["_enabled"]:
                        run_instance = RunInstance()
                        run_instance.path = instance
                        run_instance.load()
                        self.add(run_instance)

    def load_all(self):
        self.run_instances = []
        p = str(Path(f'{self.instances_path}/*'))
        instances = glob.glob(p)
        for instance in instances:
            self.load(instance)

    def run(self):
        if not self.is_running():
            pbgdir = Path.cwd()
            cmd = [sys.executable, '-u', PurePath(f'{pbgdir}/PBRun.py')]
            if platform.system() == "Windows":
                creationflags = subprocess.DETACHED_PROCESS
                creationflags |= subprocess.CREATE_NO_WINDOW
                subprocess.Popen(cmd, stdout=None, stderr=None, cwd=pbgdir, text=True, creationflags=creationflags)
            else:
                subprocess.Popen(cmd, stdout=None, stderr=None, cwd=pbgdir, text=True, start_new_session=True)
            count = 0
            while True:
                if count > 5:
                    print(f'{datetime.now().isoformat(sep=" ", timespec="seconds")} Error: Can not start PBRun')
                sleep(1)
                if self.is_running():
                    break
                count += 1

    def stop(self):
        if self.is_running():
            print(f'{datetime.now().isoformat(sep=" ", timespec="seconds")} Stop: PBRun')
            psutil.Process(self.my_pid).kill()

    def restart_pbrun(self):
        if self.is_running():
            self.stop()
            self.run()

    def is_running(self):
        self.load_pid()
        try:
            if self.my_pid and psutil.pid_exists(self.my_pid) and any(sub.lower().endswith("pbrun.py") for sub in psutil.Process(self.my_pid).cmdline()):
                return True
        except psutil.NoSuchProcess:
            pass
        return False
    
    def load_pid(self):
        if self.pidfile.exists():
            with open(self.pidfile) as f:
                pid = f.read()
                self.my_pid = int(pid) if pid.isnumeric() else None

    def save_pid(self):
        self.my_pid = os.getpid()
        with open(self.pidfile, 'w') as f:
            f.write(str(self.my_pid))


def main():
    pbgdir = Path.cwd()
    dest = Path(f'{pbgdir}/data/logs')
    if not dest.exists():
        dest.mkdir(parents=True)
    logfile = Path(f'{str(dest)}/PBRun.log')
    sys.stdout = TextIOWrapper(open(logfile,"ab",0), write_through=True)
    sys.stderr = TextIOWrapper(open(logfile,"ab",0), write_through=True)
    print(f'{datetime.now().isoformat(sep=" ", timespec="seconds")} Start: PBRun')
    run = PBRun()
    if run.is_running():
        sys.stdout = sys.__stdout__
        sys.stderr = sys.__stderr__
        print(f'{datetime.now().isoformat(sep=" ", timespec="seconds")} Error: PBRun already started')
        exit(1)
    run.save_pid()
    run.load_all()
    count = 0
    while True:
        try:
            if logfile.exists():
                if logfile.stat().st_size >= 1048576:
                    logfile.replace(f'{str(logfile)}.old')
                    sys.stdout = TextIOWrapper(open(logfile,"ab",0), write_through=True)
                    sys.stderr = TextIOWrapper(open(logfile,"ab",0), write_through=True)
            run.has_restart()
            run.has_update()
            for run_instance in run:
                run_instance.watch()
            if count%2 == 0:
                for run_instance in run:
                    run_instance.clean_log()
            sleep(5)
            count += 1
        except Exception as e:
            print(f'Something went wrong, but continue {e}')

if __name__ == '__main__':
    main()