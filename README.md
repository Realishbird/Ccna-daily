# CCNA Daily

A self-hosted study app for the Cisco CCNA 200-301 exam. It runs on your home network and gives you one required study session every day:

1. **Flash cards** with spaced repetition (due cards plus up to 30 new ones from today's topic)
2. **Subnetting drill**: timed, randomly generated problems (network/broadcast, host ranges, masks, wildcards, VLSM sizing, IPv6)
3. **Practice questions** in exam style, weighted toward your weak topics
4. **Troubleshooting lab**: read real-looking `show` output and find the root cause

The blocks unlock in order. The day counts toward your streak only when all four are done. If you are not finished by noon or the evening, you get a reminder. Once the day is done, **Extra practice** opens so you can study ahead or keep drilling.

Topics follow the official [CCNA 200-301 v1.1 exam topics](https://learningcontent.cisco.com/documents/marketing/exam-topics/200-301-CCNA-v1.1.pdf). Routing and subnetting get extra weight.

## Install on Proxmox

### Option A: one command on the Proxmox host

Open the shell of your Proxmox node and run:

```bash
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Realishbird/ccna-daily/main/deploy/create-lxc.sh)"
```

This creates an unprivileged Debian 12 container (1 core, 512 MB RAM, 4 GB disk, DHCP on `vmbr0`) and installs the app. When it finishes it prints the URL, for example `http://192.168.1.50:8080`.

Change the defaults with variables in front of the command:

```bash
CTID=150 STORAGE=local-zfs BRIDGE=vmbr0 IP=192.168.1.50/24 GW=192.168.1.1 \
  bash -c "$(curl -fsSL https://raw.githubusercontent.com/Realishbird/ccna-daily/main/deploy/create-lxc.sh)"
```

### Option B: an LXC you already have

Inside any Debian or Ubuntu container, as root:

```bash
curl -fsSL https://raw.githubusercontent.com/Realishbird/ccna-daily/main/deploy/install.sh | bash
```

### Update

Run the install script again. It pulls the latest code and restarts the service, and your progress is kept:

```bash
bash /root/install.sh        # inside the container
```

## Settings

Settings live in `/etc/ccna-daily.env`. Edit the file, then run `systemctl restart ccna-daily`.

| Setting | Default | Meaning |
| --- | --- | --- |
| `CCNA_TZ` | container time zone | Decides when a "day" starts and when reminders fire |
| `CCNA_REMINDERS` | `12:00,19:00` | Reminder times, sent only if today is not done |
| `CCNA_NTFY_URL` | empty | e.g. `https://ntfy.sh/ccna-yourname-8f3k2`; subscribe to the same topic in the ntfy phone app |
| `CCNA_DISCORD_WEBHOOK` | empty | Discord channel webhook, as an alternative |
| `CCNA_APP_URL` | `http://<ip>:8080` | Link opened when you tap a reminder |
| `CCNA_NEW_CARDS` | `30` | New flash cards per day |
| `CCNA_DRILL_MIN` | `20` | Subnetting problems per day |
| `CCNA_QUESTIONS_MIN` | `20` | Practice questions per day |
| `CCNA_LABS_MIN` | `1` | Labs per day |
| `CCNA_PORT` | `8080` | Web port |

Missing a day rolls half of that day's drill and question work into the next day.

### Phone

Open the URL in Safari or Chrome and choose **Add to Home Screen** so it opens like an app. For reminders, install **ntfy** (iOS or Android), subscribe to your topic, and put the same topic URL in `CCNA_NTFY_URL`.

## Backups

All progress is in one SQLite file: `/var/lib/ccna-daily/ccna.db`. Proxmox snapshots or `vzdump` of the container cover it.

## Content

Cards, questions, labs and the day-by-day plan are YAML files in `content/`:

- `content/schedule.yaml`: which topics each day covers
- `content/cards/*.yaml`: flash cards (`front`, `back`)
- `content/questions/*.yaml`: questions (`options`, `answer` index or list of indexes, `explain`, optional `exhibit`)
- `content/labs/*.yaml`: troubleshooting labs (`outputs` of show commands, `options`, `answer`, `explain`)

After you edit content, restart the service. `pytest` checks that every file loads and every answer index is valid.

## Development

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn ccna_daily.app:app --reload --port 8080
pytest
```

## Roadmap

- Mini exams in the real exam format: timed, no going back, and simlets
- A built-in IOS-style command line for configuration labs
- Content for domains 2, 4, 5 and 6 (VLANs/STP, services, security, automation), added before each topic's day in the plan
- Full 120-minute mock exams
