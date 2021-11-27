from datetime import datetime, timedelta
import json
from xml.etree import ElementTree


ATTEMPTS_INPUT_FILENAME = 'attempts.xml'
CONTEST_INPUT_FILENAME = 'contest.xml'
TEAMS_INPUT_FILENAME = 'teams.json'
OUTPUT_FILENAME = 'standings.json'

CATS_DATETIME_FORMAT = '%d.%m.%Y %H:%M'
ICPC_DATETIME_FORMAT = '%Y-%d-%mT%H:%M:%S.%f+10'
ICPC_TIME_FORMAT = '{}:{:02d}:{:02d}.{:03d}'


def read_attempts(filename, id_map, start_time):
    start_datetime = datetime.strptime(start_time, ICPC_DATETIME_FORMAT)

    def parse_attempt(xml_attempt: ElementTree.Element):
        attempt_data = dict((child.tag, child.text) for child in xml_attempt)

        if attempt_data['team_id'] not in id_map:
            return None

        days = float(attempt_data['time_since_start'])
        time_from_start = min(timedelta(days=days) + timedelta(seconds=30), timedelta(hours=5))

        contest_time = ICPC_TIME_FORMAT.format(time_from_start.seconds // 3600,
                                               (time_from_start.seconds // 60) % 60,
                                               time_from_start.seconds % 60,
                                               0)

        attempt_datetime = (start_datetime + time_from_start).strftime(ICPC_DATETIME_FORMAT)

        submission = {
            'id': parse_attempt.counter,
            'problem_id': attempt_data['code'],
            'team_id': id_map[attempt_data['team_id']],
            'language_id': '1',
            'files': [],
            'contest_time': contest_time,
            'time': attempt_datetime
        }
        state = attempt_data['short_state']
        judgement = {
            'id': parse_attempt.counter,
            'submission_id': parse_attempt.counter,
            'judgement_type_id': 'OK' if state == 'OK' else ('CE' if state == 'CE' else 'NA'),
            'start_contest_time': contest_time,
            'start_time': attempt_datetime,
            'end_contest_time': contest_time,
            'end_time': attempt_datetime
        }

        parse_attempt.counter += 1
        return submission, judgement

    parse_attempt.counter = 1

    xml_attempts = ElementTree.parse(filename).getroot().findall('req')
    attempts = list(map(parse_attempt, xml_attempts))
    attempts = list(filter(lambda x: x is not None, attempts))
    return attempts


def read_contest(filename):
    contest_root = ElementTree.parse(filename).getroot()

    contest_id = contest_root.find('Id').text
    title = contest_root.find('Title').text

    start_time = contest_root.find('StartDate').text
    start_time = datetime.strptime(start_time, CATS_DATETIME_FORMAT)

    finish_datetime = contest_root.find('FinishDate').text
    finish_datetime = datetime.strptime(finish_datetime, CATS_DATETIME_FORMAT)
    finish_datetime += timedelta(minutes=1)

    duration = (finish_datetime - start_time).seconds
    duration = ICPC_TIME_FORMAT.format(duration // 3600, (duration % 3600) // 60, duration % 60, 0)

    freeze_datetime = contest_root.find('FreezeDate').text
    freeze_datetime = datetime.strptime(freeze_datetime, CATS_DATETIME_FORMAT)

    scoreboard_freeze_duration = (finish_datetime - freeze_datetime).seconds
    scoreboard_freeze_duration = ICPC_TIME_FORMAT.format(scoreboard_freeze_duration // 3600, (scoreboard_freeze_duration % 3600) // 60, scoreboard_freeze_duration % 60, 0)

    start_time = start_time.strftime(ICPC_DATETIME_FORMAT)
    start_time = start_time[:-6] + start_time[-3:]
    problems = [problem.find('Code').text for problem in contest_root.findall('Problem')]

    contest = {
        'id': contest_id,
        'name': title,
        'formal_name': title,
        'start_time': start_time,
        'duration': duration,
        'scoreboard_freeze_duration': scoreboard_freeze_duration,
        'penalty_time': 20,
    }
    return contest, problems


def read_teams(filename):
    def pred(x):
        return x['ooc'] == 0 and x['virtual'] == 0 and x['jury'] == 0 and x['role'] == 'in_contest'

    def only_what_we_need(x):
        return str(x['account_id']), x['name'], x['tag']

    with open(filename, encoding='UTF-8') as input_file:
        parsed = json.loads(input_file.read())
        teams = list(map(only_what_we_need, filter(pred, parsed['users'])))

        id_map = {}
        for i in range(len(teams)):
            id_map[teams[i][0]] = i + 1
            teams[i] = (i + 1, (teams[i][1], teams[i][2]))

        return dict(teams), id_map


def write_icpc_command(t, data, file):
    command = {
        'type': t,
        'id': 'icpc{}'.format(write_icpc_command.next_id),
        'op': 'create',
        'data': data
    }
    write_icpc_command.next_id += 1
    print(json.dumps(command, ensure_ascii=False), file=file)


write_icpc_command.next_id = 0


def write_data(attempts, contest, problems, teams):
    with open(OUTPUT_FILENAME, mode='w') as output_file:
        write_icpc_command('contests', contest, output_file)
        write_icpc_command('languages', {'id': 1, 'name': ''}, output_file)
        write_icpc_command('judgement-types',
                           {'id': 'OK', 'name': 'Accepted', 'penalty': False, 'solved': True},
                           output_file)
        write_icpc_command('judgement-types',
                           {'id': 'CE', 'name': 'Compile Error', 'penalty': False, 'solved': False},
                           output_file)
        write_icpc_command('judgement-types',
                           {'id': 'NA', 'name': 'Not accepted', 'penalty': True, 'solved': False},
                           output_file)

        for i in range(len(problems)):
            problem = problems[i]
            problem_data = {
                'id': problem,
                'label': problem,
                'name': problem,
                'ordinal': i,
                'color': 'black',
                'rgb': '#000000'
            }
            write_icpc_command('problems', problem_data, output_file)

        awards = {}
        for team_id, (name, tag) in teams.items():
            organization_data = {
                'id': team_id,
                'icpc_id': None,
                'name': name,
                'formal_name': name,
                'country': 'Russia'
            }
            teams_data = {
                'id': team_id,
                'icpc_id': None,
                'name': name,
                'organization_id': team_id
            }

            if tag not in awards:
                awards[tag] = []
            awards[tag].append(str(team_id))

            write_icpc_command('organizations', organization_data, output_file)
            write_icpc_command('teams', teams_data, output_file)

        for submission, judgement in attempts:
            write_icpc_command('submissions', submission, output_file)
            write_icpc_command('judgements', judgement, output_file)


def main():
    contest, problems = read_contest(CONTEST_INPUT_FILENAME)
    teams, id_map = read_teams(TEAMS_INPUT_FILENAME)
    attempts = read_attempts(ATTEMPTS_INPUT_FILENAME, id_map, contest['start_time'])

    write_data(attempts, contest, problems, teams)


if __name__ == '__main__':
    main()
