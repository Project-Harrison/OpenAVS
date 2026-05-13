from . import navigation
import datetime
from . import supporting
from csv import reader
from copy import deepcopy

class Vessel:
    def __init__(self, name, course, speed, origin, behavior = None, tagColor = (220, 53, 68)):

        # Identifiers
        self.name = name
        self.type = None

        # Voyage
        self.date = datetime.datetime.today()
        self.voyage = supporting.identifier(6)

        # Behavior
        self.behavior = behavior

        # Posture
        self.p1 = origin
        self.course = navigation.reciprocalCourse(course)
        self.speed = speed
        self.rot = 0
        self.augment = False

        # Time
        self.minutes = datetime.datetime.today().replace(hour=0, minute=0, second=0)

        # Own and other vessels. Ordered list.
        self.ownVessel = None
        self.allVessels = None
        self.otherVessels = None

        # Other bots closest point of approach. Ordered list.
        self.cpaName = []
        self.cpa = []
        self.tcpa = []
        self.positionOther = []

        # Simulation Parameters
        self.offset = 60
        self.interval = 1

        # Tag color. Default is crimson red.
        self.color = tagColor

    def reset(self):
        """
        Summary: resets position for a simulation
        :param: offset, interval
        :return: position, course, and speed
        """

        # Adjust position backwards from origin. Typically one (1) hour.
        for plotInTime in range(0, self.offset, self.interval):
            self.p1 = navigation.arrival(self.p1, self.course, self.speed * (self.interval / 60))

        # Obtain reciprocal course.
        self.course = navigation.reciprocalCourse(self.course)

    def aware(self):

        fileExtension = 'database/stream'
        try:
            numberOfBots = len(self.allVessels)
        except:
            numberOfBots = 3

        self.cpaName = []
        self.cpa = []
        self.tcpa = []
        self.positionOther = []

        # Obtain vessel stream from database
        with open(fileExtension, 'r') as read_obj:
            csv_reader = reader(read_obj)
            allVessels = list(csv_reader)
            vesselList = allVessels[-numberOfBots:]

        # Cycle through vessels
        for num, vessel in enumerate(vesselList):

            # Obtain vessel identification and posture
            voyage = vesselList[num][0]
            vesselName = vesselList[num][1]
            p2 = (float(vesselList[num][3]), float(vesselList[num][4]))
            c2 = float(vesselList[num][5])
            s2 = float(vesselList[num][6])

            # Obtain ownship position
            p1 = deepcopy(self.p1)

            # Reset conditional parameters
            count = 0
            cpas = []
            tcpas = []

            # Advance other vessel's position and intended course one interval to align with head object.
            p2 = navigation.arrival(p2, c2, (self.interval / 60 * s2))

            # Initiate dead reckoning solution
            while True:
                # Time of event
                count += self.interval
                # Own vessel
                p1 = navigation.arrival(p1, self.course, (count / 60 * self.speed))
                # Other vessel
                p2 = navigation.arrival(p2, c2, (count / 60 * s2))
                # Unknown bug here, thus why exceptions case.
                try:
                    newCPA = navigation.distanceGreat(p1, p2)
                except:
                    # UNKNOWN BUG #1
                    newCPA = -999

                cpas.append(newCPA)
                tcpas.append(count)

                # UNKNOWN BUG #2
                # System will crash if following snippet not present
                if count >= (self.offset + self.interval):
                    break

            if cpas:
                cpaOutcome = min(cpas)
                tcpaOutcome = tcpas[cpas.index(cpaOutcome)]

                if self.voyage == voyage:
                    pass
                else:
                    self.cpaName.append(vesselName)
                    self.cpa.append(cpaOutcome)
                    self.tcpa.append(tcpaOutcome)
                    self.positionOther.append((float(vesselList[num][3]), float(vesselList[num][4])))

        return

    def stream(self):
        row = self.voyage + ',' + self.name + ',' + str(self.date) + ',' + str(self.p1[0]) + ',' + \
              str(self.p1[1]) + ',' + str(self.course) + ',' + str(self.speed) + '\n'

        with open('database/stream', 'a') as write_obj:
            write_obj.write(row)
            pass

    def advance(self, vessel):

        """
        Summary: advance a position
        :param: position, course, distance (interval - in minutes - is necessary)
        :return: new object position, new object time
        """

        # Advance position
        self.p1 = navigation.arrival(self.p1, self.course, self.speed * (self.interval / 60))

        # Advance time
        self.minutes = self.minutes + datetime.timedelta(minutes=self.interval)

        # Advance CPAs
        self.aware()

        # Instantiate database
        self.stream()


