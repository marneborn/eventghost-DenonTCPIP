import eg
import socket
import re
import time
import sys
import wx

eg.RegisterPlugin(
    name = "DenonTCPIP",
    author = "Mikael Arneborn",
    version = "0.0.1",
    kind = "other",
    description = "plugin to control my denon receiver via TCP/IP"
)

class Volume:
    def __init__(self):
        self.value   = 50.0
        self.max     = 90.0
        self.min     = 0.0
        self.startedStep = None
        self.steps   = ((0,0.5),(0.5,1),(2,2),(3,4))
    def set (self, value):
        if (self.value > self.max):
            self.value = self.max
        elif (self.value < self.min):
            self.value = self.min
        else:  
            self.value = value
    def resetStep(self):
        self.startedStep = None
    def pickStep(self):
        if (self.startedStep is None):
            self.startedStep = time.clock()
            deltaT = 0
        else:
            deltaT = time.clock()-self.startedStep
        step = 0
        for (t,s) in self.steps:
            if (t > deltaT):
                break
            step = s
        return step

    def step(self,mult):
        self.set(self.value + mult*self.pickStep())
        
class DenonVolume(Volume):
    def toSend(self):
        s = "";
        if (self.value < 10):
            s = "0"
        s = s+str(int(self.value))
        if (int(s) != int(round(self.value+0.001,0))):
            s = s+"5"
        return s
    def set(self, value):
        if (type(value) == int or type(value) == float):
            Volume.set(self, value)
        elif (type(value) != str):
            pass
        elif (len(value) == 3):
            Volume.set(self, float(value)/10)
        elif (len(value) == 2):
            Volume.set(self, float(value))
        
class DenonTCPIP(eg.PluginBase):
    """ A plugin to control my Denon Receiver via TCP/IP """
    
    def __init__(self):
        self.host = "192.168.1.2"
        self.port = 23
        self.things = []
        self.connected = False
        self.volume = DenonVolume()
        self.volume.plugin = self
        self.mute   = False
        self.AddAction(GenericSend)
        self.AddAction(ToggleMute)
        self.AddAction(InitVolume)
        self.AddAction(VolumeUp)
        self.AddAction(VolumeDn)
        self.AddAction(SetSource)
        self.AddAction(GetSource)

    def Configure(self,
                  host="192.168.1.104",
                  port=23
                  ):

        panel    = eg.ConfigPanel()
        hostCtrl = panel.TextCtrl(host)
        portCtrl = panel.SpinIntCtrl(port, max=65535)
        
        st1 = panel.StaticText("Host:")
        st2 = panel.StaticText("Port:")

        eg.EqualizeWidths((st1, st2))
        IPBox = panel.BoxedGroup(
            "TCPIP/IP Settings",
            (st1, hostCtrl),
            (st2, portCtrl),
        )

        panel.sizer.Add(IPBox, 0, wx.EXPAND)

        while panel.Affirmed():
            panel.SetResult(
                hostCtrl.GetValue(),
                portCtrl.GetValue(),
            )
            
    def __start__ (self, host, port):
        self.host = host
        self.port = port

    def __stop__ (self):
        pass

    def connect (self):
        if (self.connected):
            self.PrintError("DenonTCPIP - Already connected.")
            return True
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.settimeout(1.0)
        try:
            self.socket.connect((self.host, self.port))
            self.connected = True
            return True
        except:
            if eg.debugLevel:
                eg.PrintTraceback()
            self.PrintError("DenonTCPIP - Couldn't connect to receiver")
            self.disconnect()
            return False

    def disconnect(self):
        if (self.connected):
            self.socket.close()
            del self.socket
        self.connected = False
        return True

    def send(self, str):
        if (not self.connected):
            self.connect()
        cmd = str+"\r"
        if (sys.version_info[0] < 3):
            self.socket.sendall(cmd)
        else:
            self.socket.sendall(cmd.encode("utf-8"))

    def recv(self):
        if (not self.connected):
            self.PrintError("DenonTCPIP - Tried to receive, but there is no connection")
        r = self.socket.recv(1024)
        if (sys.version_info[0] < 3):
            return r
        else:
            return r.decode("utf-8")
        
    def getMute (self):
        self.send("MU?")
        m = self.recv()
        if (m == "MUOFF\r"):
            self.mute = False
        elif (m == "MUON\r"):
            self.mute = True
        else:
            self.PrintError("Couldn't get the mute status")

    def getsource (self):
        self.send("SI?")
        si = self.recv()
	print("Source="+si)

    def getVolume(self):
        self.send("MV?")
        v = self.recv()
        vg = re.match("MV(\d+)", v)
        if (vg is None):
            self.PrintError("DenonTCPIP - Asked for volume but got back: "+v)
        else:
            self.volume.set(vg.group(1))

    def fade(self, mult):
        firstDelay = 0.3
        startDelay = 0.3
        endDelay   = 0.3
        sweepTime  = 5.0

        while(True):
            self.volume.step(mult)
            self.send("MV"+self.volume.toSend())
            event = eg.event
            if event.shouldEnd.isSet():
                break
            elapsed = time.clock() - event.time
            if elapsed < firstDelay * 0.90:
                delay = firstDelay
            elif sweepTime > 0.0:
                sweepDelay = (
                    (startDelay - endDelay)
                    * (sweepTime - (elapsed + firstDelay))
                    / sweepTime
                )
                if sweepDelay < 0:
                    sweepDelay = 0
                delay = sweepDelay + endDelay
            else:
                delay = endDelay
            event.shouldEnd.wait(delay)

class GenericSend(eg.ActionBase):
    """Send a string"""

    def Configure(self, cmd="192.168.1.1", payload="", times=1):

        panel       = eg.ConfigPanel()
        cmdCtrl     = panel.TextCtrl(cmd)
        payloadCtrl = panel.TextCtrl(str(payload))
        timesCtrl   = panel.TextCtrl(str(times))
        
        st1 = panel.StaticText("Command:")
        st2 = panel.StaticText("Payload:")
        st3 = panel.StaticText("Times:")

        eg.EqualizeWidths((st1, st2, st3))
        cmdBox = panel.BoxedGroup(
            "Command to send",
            (st1, cmdCtrl),
            (st2, payloadCtrl),
            (st3, timesCtrl),
        )

        panel.sizer.Add(cmdBox, 0, wx.EXPAND)

        while panel.Affirmed():
            panel.SetResult(
                cmdCtrl.GetValue(),
                payloadCtrl.GetValue(),
                timesCtrl.GetValue(),
            )

    def __call__(self, cmd, payload, times):
        self.plugin.Send(cmd, payload, times)

class InitVolume(eg.ActionBase):
    """ query the receiver to the volume """
    def __call__(self):
        self.plugin.connect()
        self.plugin.getVolume()
        self.plugin.volume.resetStep()
        self.plugin.disconnect()

class VolumeUp(eg.ActionBase):
    """ Raise the volume """
    def __call__(self):
        self.plugin.connect()
        self.plugin.fade(1)
        self.plugin.disconnect()
        
class VolumeDn(eg.ActionBase):
    """ Lower the volume """
    def __call__(self):
        self.plugin.connect()
        self.plugin.fade(-1)
        self.plugin.disconnect()

class ToggleMute(eg.ActionBase):
    """Toggle the mute"""
    def __call__(self):
        self.plugin.connect()
        self.plugin.getMute()
        if (self.plugin.mute):
            self.plugin.send("MUOFF")
        else:
            self.plugin.send("MUON")
        self.plugin.disconnect()

class SetSource(eg.ActionBase):
    """Set the source"""
    def Configure(self, source=""):
        panel       = eg.ConfigPanel()
	choices = ['PHONO', 'CD', 'TUNER', 'DVD', 'HDP', 'TV/CBL', 'SAT', 'VCR', 'DVR', '.AUX', 'NET/USB', 'XM', 'IPOD', 'SAT/CBL', 'GAME']

	sourceCtrl = wx.ComboBox(panel, choices=choices)
        st2 = panel.StaticText("Source:")
        st3 = panel.StaticText("Other:")
        cmdBox = panel.BoxedGroup(
            "Source to change to",
            (st2, sourceCtrl),
        )

        panel.sizer.Add(cmdBox, 0, wx.EXPAND)

        while panel.Affirmed():
            panel.SetResult(
                sourceCtrl.GetValue(),
            )

    def __call__(self, source):
        self.plugin.connect()
        self.plugin.send("SI"+source)
        self.plugin.disconnect()

class GetSource(eg.ActionBase):
    """Get the source"""
    def __call__(self):
        self.plugin.connect()
        self.plugin.send("SI?")
        m = self.plugin.recv()
        self.plugin.disconnect()
	print("Source = "+m)
