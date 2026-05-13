from . import navigation








# Kimagure (Inky) fickle - He is the least predictable out of the four ghosts.
# Machibuse (Pinky) to ambush (with Blinky) - special case  - She is more likely to ambush the player than the other ghosts.
# Otoboke (Clyde) feigning ignorance  He prefers to wander off on his own.







class Oikake: #Chase
    def __init__(self):

        """
        Oikake (Blinky): to pursue - He is the most aggressive out of the four ghosts.
        """

        self.aggression = 12.5

    def execute(self, course, bearing):

        # Turns more aggressively if further away from head
        factor = abs((course - bearing) / self.aggression)

        if bearing > course: course += factor
        elif bearing < course: course -= factor
        else: pass

        # Standardizes course
        course = navigation.changeCourse(course)

        return course

    def go(self, vessel):

        try:
            # get other vessel's position
            otherPosition = vessel.positionOther[0]

            # Get bearing to other position
            bearing = navigation.bearing(vessel.p1, otherPosition)

            # Turn vessel in correct direction
            vessel.course = self.execute(vessel.course, bearing)
        except:
            pass

        return








# minCPA = min(ownBot.cpa)
# ind = ownBot.cpa.index(minCPA)

#p1 = ownBot.positionAtCPA(ind)













