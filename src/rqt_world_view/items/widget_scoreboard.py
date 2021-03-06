from python_qt_binding.QtWidgets import QFrame, QGridLayout, QLabel

import utils.referee as referee
from rqt_world_view.utils import utils


# Scoreboard widget.
class WidgetScoreboard(QFrame):

    # us_color: QColor() => The color to use for our team info.
    # them_color: QColor() => The color to use for their team info.
    def __init__(self, us_color, them_color):
        super(WidgetScoreboard, self).__init__()

        self.setLayout(QGridLayout())

        self.us_info = WidgetTeamInfo(us_color)
        self.them_info = WidgetTeamInfo(them_color)

        self.stage = QLabel("Stage")
        self.stage_time_left = QLabel(utils.millis_to_human_readable(0))

        # ---- Layout ----

        self.setSizePolicy(self.sizePolicy().Minimum, self.sizePolicy().Fixed)

        self.layout().addWidget(self.us_info, 0, 0, 1, 2)
        self.layout().addWidget(self.them_info, 0, 2, 1, 2)

        self.layout().addWidget(self.stage, 0, 4)
        self.layout().addWidget(self.stage_time_left, 0, 5)


    # Updates the score board with info from a message.
    # Expects a RefereeData message.
    def update_with_message(self, message):

        self.us_info.update_with_message(message.us)
        self.them_info.update_with_message(message.them)

        self.stage.setText(referee.stage_to_string(message.stage))
        self.stage_time_left.setText(utils.millis_to_human_readable(message.stage_time_left))


# Team info widget.
class WidgetTeamInfo(QFrame):

    # color: QColor() => The color to use for the border.
    def __init__(self, color):
        super(WidgetTeamInfo, self).__init__()

        self.setSizePolicy(self.sizePolicy().Minimum, self.sizePolicy().Fixed)
        self.setLayout(QGridLayout())

        self.setObjectName("score")
        self.setStyleSheet("#score { border: 3px solid rgb(" + str(color.red()) + "," + str(color.green()) + "," + str(color.blue()) + "); }")

        self.name = QLabel("NoName")
        self.score = QLabel(str(0))

        self.layout().addWidget(self.name, 0, 0)
        self.layout().addWidget(self.score, 0, 1)

    # Updates the score board with info from a message.
    # info => RefereeTeamInfoMessage
    def update_with_message(self, info):
        self.name.setText(info.name)
        self.score.setText(str(info.score))
