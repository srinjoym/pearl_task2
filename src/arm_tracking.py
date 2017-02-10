#!/usr/bin/env python

import sys
import rospy
import moveit_commander
import moveit_msgs.msg
import moveit_msgs.srv
import geometry_msgs.msg
import std_msgs.msg
import wpi_jaco_msgs.msg
import wpi_jaco_msgs.srv
import time
import requests
import tf
from ar_track_alvar_msgs.msg import *
from interactive_markers.interactive_marker_server import *
from visualization_msgs.msg import *
from math import pi, floor, ceil, fabs, sin, cos, radians

class TagTracking:

  def __init__(self, planning_frame='kinect_link', default_planner="RRTConnectkConfigDefault"):
    # r = requests.get("http://10.5.5.9/gp/gpControl/command/mode?p=1")
    # Make sure the moveit service is up and running
    rospy.logwarn("Starting up")
    rospy.init_node("tag_track")

    rospy.Subscriber('/ar_pose_marker', AlvarMarkers, self.arPoseMarkerCallback)
    
    topic = 'visualization_marker_array'
    self.publisher = rospy.Publisher(topic, MarkerArray)
    self.markerPose = [0]*3
    rospy.spin()

  def arPoseMarkerCallback(self,msg):
    if(len(msg.markers)>0):
      mark = msg.markers[0]
      p = [0]*3
      p[0] = mark.pose.pose.position.x #width
      p[1] = mark.pose.pose.position.y #height
      p[2] = mark.pose.pose.position.z #depth
      self.markerPose = p

  def printMarkerPose(self):
    print self.markerPose
    
def main():
  tagTracker = TagTracking()
  while (!rospy.is_shutdown()):
    tagTracker.printMarkerPose()
    rospy.sleep(2)
  ## ask if integrate object scene from code or not
  
    ##   Assigned tarPose the current Pose of the robot 
       
  
if __name__ == '__main__':
  ## First initialize moveit_commander and rospy.  
  main()
