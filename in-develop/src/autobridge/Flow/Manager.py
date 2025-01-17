#! /usr/bin/python3.6
import sys
from collections import defaultdict
from autobridge.HLSParser.vivado_hls.HLSProjectManager import HLSProjectManager
from autobridge.HLSParser.vivado_hls.TopRTLParser import TopRTLParser
from autobridge.Device.DeviceManager import DeviceManager
from autobridge.Opt.DataflowGraph import DataflowGraph
from autobridge.Opt.Floorplan import Floorplanner
from autobridge.Opt.GlobalRouting import GlobalRouting
from autobridge.Opt.SlotManager import SlotManager
from autobridge.Opt.LatencyBalancing import LatencyBalancing
import logging
import json
import re
import os

class Manager:

  def __init__(
      self,
      config_file_path):
    assert os.path.isfile(config_file_path)
    self.config = json.loads(open(config_file_path, 'r').read())
    self.basicSetup()
    self.loggingSetup()

    hls_prj_manager = HLSProjectManager(self.top_rtl_name, self.hls_prj_path, self.hls_solution_name)
    top_rtl_parser = TopRTLParser(hls_prj_manager.getTopRTLPath())
    graph = DataflowGraph(hls_prj_manager, top_rtl_parser)

    slot_manager = SlotManager(self.board)

    user_constraint_s2v = self.parseUserConstraints(graph, slot_manager)

    floorplan = self.runFloorplanning(graph, user_constraint_s2v, slot_manager, hls_prj_manager)

    # grid routing of edges 
    global_router = GlobalRouting(floorplan, top_rtl_parser, slot_manager)

    # latency balancing
    rebalance = LatencyBalancing(graph, floorplan, global_router)

    # TODO: code gen

  def basicSetup(self):
    self.device_manager = DeviceManager(self.config["Board"])
    self.board = self.device_manager.getBoard()

    self.top_rtl_name = self.config["TopName"]
    self.hls_prj_path = os.path.abspath(self.config["HLSProjectPath"])
    self.hls_solution_name = self.config["HLSSolutionName"]
    if "LoggingLevel" in self.config:
      self.logging_level = self.config["LoggingLevel"]
    else:
      self.logging_level = "INFO"

    if "Target" in self.config:
      self.target = self.config["Target"]
    else:
      self.target = "hw"

  def loggingSetup(self):
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    formatter = logging.Formatter("[%(levelname)s: %(funcName)25s() ] %(message)s")
    
    debug_file_handler = logging.FileHandler(filename='autobridge-debug.log', mode='w')
    debug_file_handler.setLevel(logging.DEBUG)
    info_file_handler = logging.FileHandler(filename='autobridge-info.log', mode='w')
    info_file_handler.setLevel(logging.INFO)
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(logging.INFO)

    handlers = [debug_file_handler, info_file_handler, stdout_handler]
    for handler in handlers:
      handler.setFormatter(formatter)
      root.addHandler(handler)

  def parseUserConstraints(self, graph, slot_manager):
    user_constraint_s2v = defaultdict(list)
    if "Floorplan" in self.config:
      user_fp_json = self.config["Floorplan"]
      for region, v_name_group in user_fp_json.items():
        slot = slot_manager.createSlot(region)
        for v_name in v_name_group:
          user_constraint_s2v[slot].append(graph.getVertex(v_name))

    return user_constraint_s2v

  def runFloorplanning(self, graph, user_constraint_s2v, slot_manager, hls_prj_manager, grouping_constraints=[]):
    floorplan = Floorplanner(
      graph, 
      user_constraint_s2v, 
      slot_manager=slot_manager, 
      total_usage=hls_prj_manager.getTotalArea(), 
      board=self.device_manager.getBoard(),
      user_max_usage_ratio=self.config['AreaUtilizationRatio'],
      grouping_constrants=grouping_constraints)
    
    if 'FloorplanMethod' in self.config:
      choice = self.config['FloorplanMethod']
      if choice == 'IterativeDivisionToFourCRs':
        floorplan.naiveFineGrainedFloorplan()
      elif choice == 'IterativeDivisionToHalfSLR':
        floorplan.coarseGrainedFloorplan()
      elif choice == 'IterativeDivisionToTwoCRs':
        floorplan.naiveTwoCRGranularityFloorplan()
      elif choice == 'EightWayDivisionToHalfSLR':
        floorplan.eightWayPartition()
      else:
        assert False, f'unsupported floorplan method: {choice}'
    else:
      floorplan.coarseGrainedFloorplan() # by default

    floorplan.printFloorplan()
    return floorplan

  def help(self):
    manual = {
      "Board" : "Choose between U250 and U280",
      "TopName" : "The name of the top-level function of the HLS design",
      "HLSProjectPath" : "Absolute path to the post-csynth HLS project",
      "HLSSolutionName" : "Name of the solution of the HLS project",
      "FloorplanMethod" : "Choose between IterativeDivisionToFourCRs and IterativeDivisionToHalfSLR",
      "AreaUtilizationRatio" : "Allowed resource usage in each slot",
      "Floorplan (optional)" : {
        "This is a comment" : "User could dictate the final location of given modules",
        "Region" : [
          "RTL module 1",
          "RTL module 2"
        ]
      },
      "LoggingLevel (optional)": "Choose between DEBUG, INFO, WARNING, CRITICAL, ERROR"
    }
    print(json.dumps(manual, indent=2))

if __name__ == "__main__":
  assert len(sys.argv) == 2, 'input the path to the configuration file'
  m = Manager(sys.argv[1])
    


