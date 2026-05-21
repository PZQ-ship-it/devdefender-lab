from __future__ import annotations

import sys


def project_briefing_room() -> int:
    from scripts.project_briefing_room import main

    return main()


def project_briefing_room_doctor() -> int:
    from scripts.project_briefing_room_doctor import main

    return main()


def project_briefing_agent_input() -> int:
    from scripts.agent_briefing_input import main

    return main()


def main() -> int:
    commands = {
        "project-briefing-room": project_briefing_room,
        "project-briefing-room-doctor": project_briefing_room_doctor,
        "project-briefing-agent-input": project_briefing_agent_input,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print("Usage: python -m devdefender_lab.cli <project-briefing-room|project-briefing-room-doctor|project-briefing-agent-input> ...", file=sys.stderr)
        return 2
    command = sys.argv.pop(1)
    return commands[command]()


if __name__ == "__main__":
    raise SystemExit(main())
