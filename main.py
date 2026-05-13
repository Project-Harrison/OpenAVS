from sim import autonomous, interface, behavior, supporting

# Clear stream database so each run starts fresh
open('database/stream', 'w').close()


def make_sim(origin):
    """Create and position all vessels for the given chart origin."""
    targetBot = autonomous.Vessel("AUG/V TargetBot", 48, 12, origin, None)

    bots = [targetBot]
    for b in bots:
        b.reset()
    supporting.segregate(bots)

    return bots, targetBot


interface.run(make_sim, 10000000)
