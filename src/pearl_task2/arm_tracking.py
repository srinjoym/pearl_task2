#!/usr/bin/env python
import sys
import rospy
import moveit_commander
import moveit_msgs.msg
import moveit_msgs.srv
from geometry_msgs.msg import *
import std_msgs.msg
import wpi_jaco_msgs.msg
import wpi_jaco_msgs.srv
import time
import operator
from vector_msgs.msg import JacoCartesianVelocityCmd, LinearActuatorCmd, GripperCmd, GripperStat
import requests
import tf2_ros
import tf2_geometry_msgs
import tf
from ar_track_alvar_msgs.msg import *
from interactive_markers.interactive_marker_server import *
from visualization_msgs.msg import *
from std_msgs.msg import *
from math import pi, floor, ceil, fabs, sin, cos, radians,degrees
import numpy

class TagTracking:

  def __init__(self, planning_frame='linear_actuator_link', default_planner="RRTConnectkConfigDefault"):
    # r = requests.get("http://10.5.5.9/gp/gpControl/command/mode?p=1")
    # Make sure the moveit service is up and running
    rospy.logwarn("Starting up")
    # rospy.init_node("tag_track")
    try:
      rospy.wait_for_service('compute_ik')
    except rospy.ROSExecption, e:
      rospy.logerr("No moveit service detected. Exiting")
      exit()
    else:
      rospy.loginfo("MoveIt detected: arm planner loading")

    self.robot = moveit_commander.RobotCommander()
    self.currentMarkerPose = geometry_msgs.msg.PoseStamped()
    self.scene = moveit_commander.PlanningSceneInterface()
    self.group = [moveit_commander.MoveGroupCommander("left_arm")] #change this to right_arm or left_arm
    self.planner = default_planner
    self.group[0].set_pose_reference_frame(planning_frame)
    self.continuous_joints = ['left_shoulder_pan_joint','left_wrist_1_joint','left_wrist_2_joint','left_wrist_3_joint']
    self.continuous_joints_list = [0,3,4,5,6,9,10,11] # joints that are continous
    
    self.kinect_angle_pub = rospy.Publisher('/tilt_controller/command',Float64)
    tfBuffer = tf2_ros.Buffer()
    listener = tf2_ros.TransformListener(tfBuffer)
    self.publisher = rospy.Publisher('visualization_marker_array', MarkerArray)
    #rospy.Subscriber('/ar_pose_marker', AlvarMarkers, self.arPoseMarkerCallback)
    rospy.sleep(2)
    
    self.kinect_angle = Float64()
    self.kinect_angle.data = 0.3925
    self.kinect_angle_pub.publish(self.kinect_angle)
    self.trans = tfBuffer.lookup_transform("linear_actuator_link","kinect_link",rospy.Time(0))
    self.gotInit=False
    self.markerArray = MarkerArray()

  def _simplify_angle(self, angle):
  # Very simple function that makes sure the angles are between -pi and pi
    if angle > pi:
      while angle > pi:
        angle -= 2*pi
    elif angle < -pi:
      while angle < -pi:
        angle += 2*pi

    return angle

  def _simplify_joints(self, joint_dict):

    if isinstance(joint_dict, dict):
      simplified_joints = dict()
      for joint in joint_dict:
        # Pull out the name of the joint
        joint_name = '_'.join(joint.split('_')[1::])
        if joint_name in self.continuous_joints:
          simplified_joints[joint] = self._simplify_angle(joint_dict[joint])
        else:
          simplified_joints[joint] = joint_dict[joint]
    elif isinstance(joint_dict, list):
      simplified_joints = []
      for i in xrange(len(joint_dict)):
        
        a = joint_dict[i]

        if i in self.continuous_joints_list:
          simplified_joints.append(self._simplify_angle(a))
        else:
          simplified_joints.append(a)
    return simplified_joints

#   '''Older functions - left for backwards compatibility'''

  def plan_jointTargetInput(self,target_joint,n):
    ## input: target joint angles (list) of the robot
    ## output: plan from current joint angles to the target one
    try:
      self.group[n].set_joint_value_target(self._simplify_joints(target_joint))
      self.group[n].set_planner_id(self.planner)
      planAns=self.group[n].plan()
      return planAns
    except:
      print 'No plan found, see the moveit terminal for the error'
      print("Unexpected error:", sys.exc_info()[0])
      return None

  def get_FK(self, root = 'linear_actuator_link'):

    rospy.wait_for_service('compute_fk')
    compute_fk = rospy.ServiceProxy('compute_fk', moveit_msgs.srv.GetPositionFK)

    header = std_msgs.msg.Header()
    header.frame_id = root
    header.stamp = rospy.Time.now()
    fk_link_names = ['left_ee_link']
    robot_state = self.robot.get_current_state()    
    try:
      reply=compute_fk(header,fk_link_names,robot_state)
      return reply.pose_stamped

    except rospy.ServiceException, e:
      print "Service call failed: %s"%e

  def get_IK(self, newPose,n, root = None):
    ## from a defined newPose (geometry_msgs.msg.Pose()), retunr its correspondent joint angle(list)
    rospy.wait_for_service('compute_ik')
    compute_ik = rospy.ServiceProxy('compute_ik', moveit_msgs.srv.GetPositionIK)

    wkPose = geometry_msgs.msg.PoseStamped()
    if root is None:
      wkPose.header.frame_id = 'linear_actuator_link' # name:odom
    else:
      wkPose.header.frame_id = root

    wkPose.header.stamp=rospy.Time.now()
    wkPose.pose=newPose

    msgs_request = moveit_msgs.msg.PositionIKRequest()
    msgs_request.group_name = 'left_arm'; # takes in left_arm as argument at all times.
    # msgs_request.ik_link_name = self.group[n].get_name()
    # print self.group[n].get_name()
    msgs_request.robot_state = self.robot.get_current_state()
    msgs_request.pose_stamped = wkPose
    msgs_request.timeout.secs = 2
    msgs_request.avoid_collisions = False
    # print msgs_request
    try:
      jointAngle=compute_ik(msgs_request)
      ans=list(jointAngle.solution.joint_state.position[1:7])
      if jointAngle.error_code.val == -31:
        print 'No IK solution'
        return None
      return ans

    except rospy.ServiceException, e:
      print "Service call failed: %s"%e


  def publish_point(self, pose,color):
    marker = Marker()
    marker.type = marker.CUBE
    marker.action = marker.ADD
    marker.scale.x = 0.1
    marker.scale.y = 0.1
    marker.scale.z = 0.1
    marker.color.a = 1.0
    marker.color.r = color[0]
    marker.color.g= color[1]
    marker.color.b = color[2]
    marker.pose = pose
    marker.header.frame_id = "/linear_actuator_link"
    # print self.marker
    #markerArray = MarkerArray()
    self.markerArray.markers.append(marker)

    id = 0
    for m in self.markerArray.markers:
      m.id = id
      id += 1
    # print self.markerArray
    self.publisher.publish(self.markerArray)

  def arPoseMarkerCallback(self,msg):
    if(len(msg.markers)>0):
      mark = msg.markers[0]
      pose = geometry_msgs.msg.PoseStamped()
      pose.header = mark.header

      #config for simulation with kinect 2
      # pose.pose.position.x = mark.pose.pose.position.z
      # pose.pose.position.y = -mark.pose.pose.position.x
      # pose.pose.position.z = -mark.pose.pose.position.y
      # pose.pose.orientation.x = mark.pose.pose.orientation.z
      # pose.pose.orientation.y = -mark.pose.pose.orientation.x
      # pose.pose.orientation.z = -mark.pose.pose.orientation.y
      # pose.pose.orientation.w = mark.pose.pose.orientation.w

      pose.pose.position.x = mark.pose.pose.position.x
      pose.pose.position.y = mark.pose.pose.position.y
      pose.pose.position.z = mark.pose.pose.position.z
      pose.pose.orientation.x = mark.pose.pose.orientation.x
      pose.pose.orientation.y = mark.pose.pose.orientation.y
      pose.pose.orientation.z = mark.pose.pose.orientation.z
      pose.pose.orientation.w = mark.pose.pose.orientation.w

      if(pose.pose == self.currentMarkerPose):
        
        pass

      print "callback"
      self.gotInit = True
      # print pose
      self.currentMarkerPose = pose

  def getMarkerPose(self):
      print "Marker Pose is:"
      # print [self.currentMarkerPose[2]+self.trans[0],self.currentMarkerPose[0]+self.trans[1],self.currentMarkerPose[1]-self.trans[2]]
      # self.publish_point(self.currentMarkerPose[2]+self.trans[0],self.currentMarkerPose[0]+self.trans[1],self.currentMarkerPose[1]-self.trans[2])
      # return [self.currentMarkerPose[2]+self.trans[0],self.currentMarkerPose[0]+self.trans[1],self.currentMarkerPose[1]-self.trans[2]]
      while(not self.gotInit and not rospy.is_shutdown()):
        1==1
      print "got init doing transform"
      # return tf2_geometry_msgs.do_transform_pose(self.currentMarkerPose,self.trans)
      return self.currentMarkerPose
      

  def getRobotCurrentState(self):
    return self.group[0].get_current_pose().pose
    

  def get_goal_pos(self,marker_pos,robot_pos,goal_pos):

    diff = geometry_msgs.msg.Pose()

    diff.position.x = robot_pos.position.x - marker_pos.position.x
    diff.position.y = robot_pos.position.y - marker_pos.position.y
    diff.position.z = robot_pos.position.z - marker_pos.position.z

    angleRobot = tf.transformations.euler_from_quaternion([robot_pos.orientation.x,robot_pos.orientation.y,robot_pos.orientation.z,robot_pos.orientation.w])
    raw_angleMarker = tf.transformations.euler_from_quaternion([marker_pos.orientation.x,marker_pos.orientation.y,marker_pos.orientation.z,marker_pos.orientation.w])
    angleGoal = tf.transformations.euler_from_quaternion([goal_pos.orientation.x,goal_pos.orientation.y,goal_pos.orientation.z,goal_pos.orientation.w])

    adj_angleMarker=[0]*3
    adj_angleMarker[0]=raw_angleMarker[0] #accounting for leg being vertical in arm
    adj_angleMarker[1]=raw_angleMarker[1]
    adj_angleMarker[2]=raw_angleMarker[2]

    diffAngle = [0]*3
    diffAngle[0]=(adj_angleMarker[0]-angleRobot[0])
    diffAngle[1]=(adj_angleMarker[1]-angleRobot[1])  
    diffAngle[2]=(adj_angleMarker[2]-angleRobot[2])

    print "angle robot"
    print [degrees(angleRobot[0]),degrees(angleRobot[1]),degrees(angleRobot[2])]

    print "angle marker"
    print [degrees(adj_angleMarker[0]),degrees(adj_angleMarker[1]),degrees(adj_angleMarker[2])]

    print "diff angle"
    print [degrees(diffAngle[0]),degrees(diffAngle[1]),degrees(diffAngle[2])]

    targetAngle = [0]*3
    targetAngle[0] = angleGoal[0]-diffAngle[0]
    targetAngle[1] = angleGoal[1]-diffAngle[1]
    targetAngle[2] = angleGoal[2]-diffAngle[2]

    print "target angle"
    print targetAngle

    targetQuaternion = tf.transformations.quaternion_from_euler(targetAngle[0],targetAngle[1],targetAngle[2])

    target = geometry_msgs.msg.Pose()

    if(diff.position.x<0.1 and diff.position.y<0.1 and diff.position.z<0.1 and diffAngle[0]<radians(20) and diffAngle[1]<radians(20) and diffAngle[2]<radians(20)):
      target.position.x = goal_pos.position.x+diff.position.x
      target.position.y =goal_pos.position.y+ diff.position.y
      target.position.z = goal_pos.position.z+diff.position.z
      target.orientation.x = targetQuaternion[0]
      target.orientation.y = targetQuaternion[1]
      target.orientation.z = targetQuaternion[2]
      target.orientation.w = targetQuaternion[3]
      print "diff:"
      print diff
      print "goal"
      print goal_pos
      print "target:"
      print target
      return target
    else:
      print "error exceeded bounds"
      return goal_pos
    
  def go_home(self,count):

    pos1 = geometry_msgs.msg.Pose()
    pos1.position.x = 1.2048
    pos1.position.y = 0.209
    #goal_pos.position.z = 0.1136
    pos1.position.z = 0.21
    pos1.orientation.x =0.077
    pos1.orientation.y = 0.0064
    pos1.orientation.z = 0.044
    pos1.orientation.w = 1

    pos2 = geometry_msgs.msg.Pose()
    pos2.position.x = 1.2048
    pos2.position.y = 0.209
    #goal_pos.position.z = 0.1136
    pos2.position.z = 0.21  
    pos2.orientation.x =0.077
    pos2.orientation.y = 0.0064
    pos2.orientation.z = 0.044
    pos2.orientation.w = 1


    if(count==1):
       jointTarg = self.get_IK(pos1,0)
    else:
       joinTarg = self.get_IK(pos2,0)

    planTraj = self.plan_jointTargetInput(jointTarg,0)
    if(planTraj!=None):
        self.group[0].execute(planTraj)




  def above_hole(self,goal_pos):
    pre_goal_pos = goal_pos
    pre_goal_pos.position.z = goal_pos.position.z+0.1
    print pre_goal_pos
    self.publish_point(pre_goal_pos,[0,1,0])

    if(input("continue?")==-1):
      return

    jointTarg = self.get_IK(pre_goal_pos,0)
    planTraj = self.plan_jointTargetInput(jointTarg,0)
    if(planTraj!=None):
        self.group[0].execute(planTraj)

  def in_hole(self,goal_pos):
    goal_pos.position.z = goal_pos.position.z-0.1
    self.publish_point(goal_pos,[1,0,0])
    print goal_pos
    if(input("continue?")==-1):
      return

    jointTarg = self.get_IK(goal_pos,0)
    planTraj = self.plan_jointTargetInput(jointTarg,0)
    if(planTraj!=None):
        self.group[0].execute(planTraj)

    
def main():
  tagTracker = TagTracking()
  counter = 0
  while (not(rospy.is_shutdown())):
    # print tagTracker.get_FK()[0].pose
 

    goal_angle = tf.transformations.quaternion_from_euler(0,0,0)
    goal_pos = geometry_msgs.msg.Pose()
    goal_pos.position.x = 1.135
    goal_pos.position.y = 0.28
    #goal_pos.position.z = 0.1136
    goal_pos.position.z =-0.06
    goal_pos.orientation.x =0
    goal_pos.orientation.y = 0
    goal_pos.orientation.z = 0
    goal_pos.orientation.w = 1

    tagTracker.above_hole(goal_pos)

    robot_pos = tagTracker.get_FK()[0].pose
    #marker_pos = tagTracker.getMarkerPose().pose
    marker_pos = goal_pos
    #marker_pos = geometry_msgs.msg.Pose()
    #marker_pos.position.x = goal_pos.position.x
    #marker_pos.position.y = goal_pos.position.y
    #marker_pos.position.z = goal_pos.position.z+.1
    
    #marker_angle = tf.transformations.quaternion_from_euler(0,50,0)
    #marker_pos.orientation.x = marker_angle[0]
    #marker_pos.orientation.y = marker_angle[1]
    #marker_pos.orientation.z = marker_angle[2]
    #marker_pos.orientation.w = marker_angle[3]
    # final_goal = tagTracker.get_goal_pos(marker_pos,robot_pos,goal_pos)
    tagTracker.in_hole(goal_pos)

    print "done" + str(counter)
    counter+=1
    rospy.sleep(1)

    
    if(input("continue?")==-1):
      return
    print "going home"
    tagTracker.go_home(counter%2)
  ## ask if integrate object scene from code or not
  
    ##   Assigned tarPose the current Pose of the robot 
       
  
if __name__ == '__main__':
  ## First initialize moveit_commander and rospy.  
  moveit_commander.roscpp_initialize(sys.argv)
  rospy.init_node('arm_tracking', anonymous=True)
  main()
  rospy.spin()
