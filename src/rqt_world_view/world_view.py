import os
import rospy
import rospkg
import actionlib
import roslib
roslib.load_manifest("roboteam_msgs")

import math

from qt_gui.plugin import Plugin
from python_qt_binding import loadUi, QtCore, QtGui, QtWidgets
from python_qt_binding.QtCore import pyqtSignal
from python_qt_binding.QtWidgets import QWidget, QLabel, QGraphicsScene, QGraphicsItemGroup, QGraphicsEllipseItem, QGraphicsLineItem, QGraphicsTextItem, QGraphicsRectItem

from roboteam_msgs.msg import World as WorldMessage
from roboteam_msgs.msg import GeometryData as GeometryMessage
from roboteam_msgs.msg import RefereeData as RefboxMessage
from roboteam_msgs.msg import SteeringAction, SteeringGoal

from items.field_graphics_view import FieldGraphicsView
from items.field_graphics_scene import FieldGraphicsScene
from items.graphics_robot import GraphicsRobot
from items.widget_robot_details import WidgetRobotDetails
from items.qgraphics_arc_item import QGraphicsArcItem
from items.widget_scoreboard import WidgetScoreboard
from items.widget_blackboard import WidgetBlackboard


BOT_DIAMETER = 180 # Diameter of the bots in mm.
BALL_DIAMETER = 50


# Size of the area around the field in mm.
FIELD_RUNOUT_ZONE = 300


FIELD_COLOR = QtGui.QColor(0, 200, 50)
FIELD_LINE_COLOR = QtGui.QColor(255, 255, 255)
BALL_COLOR = QtGui.QColor(255, 100, 0)

US_COLOR = QtGui.QColor(255, 50, 50); # The color of our robots.
THEM_COLOR = QtGui.QColor(127, 84, 147); # The color of the opponents robots.

# Converts to mm.
def m_to_mm(meters):
    return meters * 1000.0

# Converts millimeters to meters.
def mm_to_m(millimeters):
    return millimeters / 1000.0


class WorldViewPlugin(Plugin):

    # Qt signal for when the world state changes.
    worldstate_signal = pyqtSignal(WorldMessage)
    # Qt signal for when the graphics calibration changes.
    geometry_signal = pyqtSignal(GeometryMessage)
    referee_signal = pyqtSignal(RefboxMessage)

    # Graphic representations of the us and them robots.
    # QGraphicsItemGroup.
    robots_us_graphic = {}
    robots_them = {}

    robots_us_sidebar = {}

    # List of selected robot id's.
    robots_us_selected = []
    robots_them_selected = []

    ball = QGraphicsEllipseItem(0, 0, BALL_DIAMETER, BALL_DIAMETER)

    field_lines = QGraphicsItemGroup()

    goals = QGraphicsItemGroup()


    # Field size in mm.
    field_width = 9000
    field_height = 6000

    field_background = QGraphicsRectItem(-field_width/2, -field_height/2, field_width, field_height)


    def __init__(self, context):
        super(WorldViewPlugin, self).__init__(context)
        # Give QObjects reasonable names
        self.setObjectName('WorldViewPlugin')

        # Process standalone plugin command-line arguments
        from argparse import ArgumentParser
        parser = ArgumentParser()
        # Add argument(s) to the parser.
        parser.add_argument("-q", "---quiet", action="store_true",
                      dest="quiet",
                      help="Put plugin in silent mode")
        args, unknowns = parser.parse_known_args(context.argv())
        if not args.quiet:
            print 'arguments: ', args
            print 'unknowns: ', unknowns


        # Create QWidget
        self.widget = QWidget()

        # Get path to UI file which should be in the "resource" folder of this package
        ui_file = os.path.join(rospkg.RosPack().get_path('roboteam_rqt_view'), 'resource', 'WorldView.ui')
        # Extend the widget with all attributes and children from UI file
        loadUi(ui_file, self.widget)

        # Give QObjects reasonable names
        self.widget.setObjectName('WorldView')

        # Show _widget.windowTitle on left-top of each plugin (when
        # it's set in _widget). This is useful when you open multiple
        # plugins at once. Also if you open multiple instances of your
        # plugin at once, these lines add number to make it easy to
        # tell from pane to pane.
        if context.serial_number() > 1:
            self.widget.setWindowTitle(self.widget.windowTitle() + (' (%d)' % context.serial_number()))
        # Add widget to the user interface
        context.add_widget(self.widget)

        # Subscribe to the world state.
        self.worldstate_sub = rospy.Subscriber("world_state", WorldMessage, self.callback_worldstate)

        # Subscribe to the geometry information.
        self.geometry_sub = rospy.Subscriber("vision_geometry", GeometryMessage, self.callback_geometry)

        # Subscribe to the referee information.
        self.referee_sub = rospy.Subscriber("vision_refbox", RefboxMessage, self.callback_referee)

        # Create the steering action client.
        self.client = actionlib.SimpleActionClient("steering", SteeringAction)

        # ---- Field view initialization ----

        self.scene = FieldGraphicsScene();
        self.fieldview = FieldGraphicsView()
        self.fieldview.setScene(self.scene)

        # Enable antialiasing.
        self.fieldview.setRenderHints(QtGui.QPainter.Antialiasing)

        # Add to the main window.
        self.widget.s_main_splitter.addWidget(self.fieldview)

        #self.fieldview.setDragMode(FieldGraphicsView.RubberBandDrag)

        self.scene.clear()

        # Add the field to the scene.
        self.scene.addItem(self.field_background)
        self.field_background.setBrush(QtGui.QBrush(FIELD_COLOR))

        # Add the field lines.
        self.scene.addItem(self.field_lines)

        # Add the goals.
        self.scene.addItem(self.goals)

        # Add the ball to the scene.
        self.scene.addItem(self.ball)
        self.ball.setBrush(QtGui.QBrush(BALL_COLOR))

        # Scale the scene so that it fits into the view area.
        self.fieldview.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

        # ---- /Field view initialization ----

        # ---- Score board ----

        self.scoreboard = WidgetScoreboard(US_COLOR, THEM_COLOR)
        # Insert it all the way at the top.
        self.widget.l_toolbar_layout.layout().insertWidget(0, self.scoreboard)

        # ---- /Score board ----

        # ---- Blackboard ----

        self.blackboard = WidgetBlackboard()
        self.widget.l_side_layout.layout().addWidget(self.blackboard)


        # ---- /Blackboard ----

        self.font = QtGui.QFont()
        self.font.setPixelSize(BOT_DIAMETER*0.8)

        # ---- Signal connections ----

        # Connect the signal sent by the worldstate callback to the message slot.
        self.worldstate_signal.connect(self.slot_worldstate)
        # Connect the Geometry callback to the Geometry slot.
        self.geometry_signal.connect(self.slot_geometry)
        self.referee_signal.connect(self.slot_referee)

        # Connect the scene's selectionChanged signal.
        self.scene.selectionChanged.connect(self.slot_selection_changed)

        # Connect the scenes right click signal.
        self.scene.right_click_signal.connect(self.slot_view_right_clicked)


        # Connect the toolbar buttons.
        self.widget.b_select_all.clicked.connect(self.slot_select_all_button)
        self.widget.b_clear_selection.clicked.connect(self.slot_clear_selection_button)
        self.widget.b_reset_view.clicked.connect(self.slot_reset_view_button)

        # ---- /Signal connections ----


    def shutdown_plugin(self):
        # TODO unregister all publishers here
        self.worldstate_sub.unregister()
        pass

    def save_settings(self, plugin_settings, instance_settings):
        # TODO save intrinsic configuration, usually using:
        # instance_settings.set_value(k, v)
        pass

    def restore_settings(self, plugin_settings, instance_settings):
        # TODO restore intrinsic configuration, usually using:
        # v = instance_settings.value(k)
        pass

    #def trigger_configuration(self):
        # Comment in to signal that the plugin has a way to configure
        # This will enable a setting button (gear icon) in each dock widget title bar
        # Usually used to open a modal configuration dialog


    # Is called when a worldstate message is received.
    def callback_worldstate(self, message):
        # Send signal to qt thread.
        self.worldstate_signal.emit(message)


    def callback_referee(self, message):
        self.referee_signal.emit(message)


    def callback_geometry(self, message):
        # Send signal to qt thread.
        self.geometry_signal.emit(message)


# ------------------------------------------------------------------------------
# ---------- Gui change slots --------------------------------------------------
# ------------------------------------------------------------------------------


    # Receives the changeUI(PyQt_PyObject) signal which gets sent when a message arrives at 'message_callback'.
    def slot_worldstate(self, message):
        # Move the ball.
        self.ball.setPos(m_to_mm(message.ball.pos.x) - BALL_DIAMETER/2, -(m_to_mm(message.ball.pos.y) - BALL_DIAMETER/2))

        # Process the us bots.
        for bot in message.us:
            if not bot.id in self.robots_us_graphic:
                # Create a graphics item for this robot.
                self.robots_us_graphic[bot.id] = GraphicsRobot(bot.id, True, US_COLOR, self.font)
                self.scene.addItem(self.robots_us_graphic[bot.id])

                # Create a list item for this robot.
                self.robots_us_sidebar[bot.id] = WidgetRobotDetails(bot.id)
                self.widget.l_robotlist_layout.addWidget(self.robots_us_sidebar[bot.id])

                # Connect the list items `change_bot_selection` signal.
                self.robots_us_sidebar[bot.id].change_bot_selection.connect(self.slot_change_robot_selected_state)

            self.robots_us_graphic[bot.id].setPos(m_to_mm(bot.pos.x), -m_to_mm(bot.pos.y))
            self.robots_us_graphic[bot.id].rotate_to(-math.degrees(bot.angle))

            # Update the sidebar.
            self.robots_us_sidebar[bot.id].update_display(bot)

        # Process the them bots.
        for bot in message.them:
            if not bot.id in self.robots_them:
                self.robots_them[bot.id] = GraphicsRobot(bot.id, False, THEM_COLOR, self.font)
                self.scene.addItem(self.robots_them[bot.id])

            self.robots_them[bot.id].setPos(m_to_mm(bot.pos.x), -m_to_mm(bot.pos.y))
            self.robots_them[bot.id].rotate_to(-math.degrees(bot.angle))


    def slot_geometry(self, message):
        self.field_width = m_to_mm(message.field.field_width)
        self.field_length = m_to_mm(message.field.field_length)

        rospy.loginfo("Field width: %i", self.field_width)
        rospy.loginfo("Field length: %i", self.field_length)

        # Resize the field background.
        self.field_background.setRect(
            -(self.field_length/2 + FIELD_RUNOUT_ZONE), -(self.field_width/2 + FIELD_RUNOUT_ZONE),
            self.field_length + FIELD_RUNOUT_ZONE * 2, self.field_width + FIELD_RUNOUT_ZONE * 2)

        # Remove all field lines.
        for item in self.field_lines.childItems():
            self.field_lines.removeFromGroup(item)
            del item

        # Remove all goals.
        for item in self.goals.childItems():
            self.goals.removeFromGroup(item)
            del item


        # Add all the lines.
        for msg_line in message.field.field_lines:
            line_pen = QtGui.QPen()
            line_pen.setColor(FIELD_LINE_COLOR)
            line_pen.setWidth(m_to_mm(msg_line.thickness))

            line = QGraphicsLineItem(
                m_to_mm(msg_line.x_begin), -m_to_mm(msg_line.y_begin),
                m_to_mm(msg_line.x_end), -m_to_mm(msg_line.y_end))
            line.setPen(line_pen)
            self.field_lines.addToGroup(line)

        # Add all the arcs.
        for msg_arc in message.field.field_arcs:
            line_pen = QtGui.QPen()
            line_pen.setColor(FIELD_LINE_COLOR)
            line_pen.setWidth(m_to_mm(msg_line.thickness))

            arc = QGraphicsArcItem(
                m_to_mm(msg_arc.x_center - msg_arc.radius), -m_to_mm(msg_arc.y_center - msg_arc.radius),
                m_to_mm(msg_arc.radius)*2, -m_to_mm(msg_arc.radius)*2)
            arc.setStartAngle(math.degrees(msg_arc.a1)*16)
            arc.setSpanAngle(math.degrees(msg_arc.a2 - msg_arc.a1)*16)
            arc.setPen(line_pen)
            self.field_lines.addToGroup(arc)

        # Create the goals.
        goal_width = m_to_mm(message.field.goal_width)
        goal_depth = m_to_mm(message.field.goal_depth)

        rospy.loginfo("Goal width: %i", goal_width)
        rospy.loginfo("Goal depth: %i", goal_depth)

        goal_x_from_center = self.field_height/2 + goal_depth
        goal_y_from_center = goal_width/2

        goal_pen = QtGui.QPen()
        goal_pen.setWidth(goal_depth / 20)

        # Left goal.

        back_line = QGraphicsLineItem(
            -goal_x_from_center, goal_y_from_center,
            -goal_x_from_center, -goal_y_from_center)
        back_line.setPen(goal_pen)
        self.goals.addToGroup(back_line)

        top_line = QGraphicsLineItem(
            -goal_x_from_center, goal_y_from_center,
            -self.field_height/2, goal_y_from_center)
        top_line.setPen(goal_pen)
        self.goals.addToGroup(top_line)

        bottom_line = QGraphicsLineItem(
            -goal_x_from_center, -goal_y_from_center,
            -self.field_height/2, -goal_y_from_center)
        bottom_line.setPen(goal_pen)
        self.goals.addToGroup(bottom_line)

        # Right goal.

        back_line = QGraphicsLineItem(
            goal_x_from_center, goal_y_from_center,
            goal_x_from_center, -goal_y_from_center)
        back_line.setPen(goal_pen)
        self.goals.addToGroup(back_line)

        top_line = QGraphicsLineItem(
            goal_x_from_center, goal_y_from_center,
            self.field_height/2, goal_y_from_center)
        top_line.setPen(goal_pen)
        self.goals.addToGroup(top_line)

        bottom_line = QGraphicsLineItem(
            goal_x_from_center, -goal_y_from_center,
            self.field_height/2, -goal_y_from_center)
        bottom_line.setPen(goal_pen)
        self.goals.addToGroup(bottom_line)


    def slot_referee(self, message):
        self.scoreboard.update_with_message(message)


    # Slot for the scenes selectionChanged signal.
    def slot_selection_changed(self):
        # Clear the selection lists.
        del self.robots_us_selected[:]

        for bot_id, bot in self.robots_us_graphic.iteritems():
            if bot.isSelected():
                self.robots_us_selected.append(bot_id)

            # Update the sidebar.
            self.robots_us_sidebar[bot_id].set_selected_state(bot.isSelected())


    # Called when the view is right clicked.
    def slot_view_right_clicked(self, event):
        #TODO: Only send actions when there is a server connected.

        for bot_id in self.robots_us_selected:
            goal_pos = event.scenePos()

            goal = SteeringGoal()
            goal.robot_id = bot_id

            # The message is in meters, on screen it is in mm.
            # So divide by 1000.
            goal.x = goal_pos.x()/1000.0
            goal.y = -goal_pos.y()/1000.0

            rospy.loginfo("Robot %i go to: %f, %f", bot_id, goal.x, goal.y)

            self.client.send_goal(goal)
            self.client.wait_for_result(rospy.Duration.from_sec(1.0))

# ------------------------------------------------------------------------------
# ---------- Button slots ------------------------------------------------------
# ------------------------------------------------------------------------------

    # Changes the selection state of a single robot.
    # bot_id: integer => The id of the bot.
    # selected: bool => Whether the robot should be selected or not.
    def slot_change_robot_selected_state(self, bot_id, selected):
        if bot_id in self.robots_us_graphic:
            self.robots_us_graphic[bot_id].setSelected(selected)

    # Called when the select all button is clicked.
    def slot_select_all_button(self):
        for bot_id, bot in self.robots_us_graphic.iteritems():
            bot.setSelected(True)

    # Called when the clear selection button is clicked.
    def slot_clear_selection_button(self):
        for bot_id, bot in self.robots_us_graphic.iteritems():
            bot.setSelected(False)

    # Called when the reset view button is clicked.
    def slot_reset_view_button(self):
        # Scale the scene so that it fits into the view area.
        self.fieldview.fitInView(self.scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
