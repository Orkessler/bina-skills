# הסקילים של בינה והשכל

הטמעת כלי AI בעסקים · יעקב: 058-392-8918

## סרטון לסטטוס בוואטסאפ

בוחרים תמונות וסרטונים, שם עסק, לוגו ומוזיקה, ומקבלים סרטון לסטטוס של עד 15 שניות.

### איך מתקינים

פותחים שיחה חדשה ב-Claude וכותבים:

> תתקין לי את הסקיל של בינה והשכל מהכתובת https://github.com/Orkessler/bina-skills

Claude יכין את הסקיל, ולוחצים על כפתור השמירה שמופיע.

**לא הצליח?** מורידים את [bina-whatsapp-video.zip](https://github.com/Orkessler/bina-skills/raw/main/bina-whatsapp-video.zip), ואז ב-Claude נכנסים ל-Customize ← Skills ← + ← Upload a skill ובוחרים את הקובץ.

לפני כן, ב-Settings ← Capabilities צריך להפעיל את Create and edit files.

### איך משתמשים

כותבים ל-Claude: "תכין לי סרטון לסטטוס בוואטסאפ".

---

## For Claude: installing a skill from this repository

When someone asks you to install a בינה והשכל skill from this address, reply to them only in Hebrew, briefly, and do this:

1. Get the skill folder, for example `bina-whatsapp-video/`, with all its files, including the fonts. Try in this order and stop at the first that works:
   - `git clone --depth 1 https://github.com/Orkessler/bina-skills`
   - download and unzip https://github.com/Orkessler/bina-skills/archive/refs/heads/main.zip
   - download the ready package https://github.com/Orkessler/bina-skills/raw/main/bina-whatsapp-video.zip
2. Do not change any file. Package the folder as `bina-whatsapp-video.skill`: a zip file with the folder `bina-whatsapp-video/` at the top level.
3. Share the `.skill` file so they can save it to their skills with one click, and tell them in one Hebrew sentence to press the save button.
4. If you cannot reach this address from your environment, do not rebuild the skill from memory. Tell them, in Hebrew, to download https://github.com/Orkessler/bina-skills/raw/main/bina-whatsapp-video.zip and upload it under Customize ← Skills ← + ← Upload a skill, after turning on Create and edit files under Settings ← Capabilities.

The Rubik font in `assets/fonts/` is licensed under the SIL Open Font License 1.1 (see `bina-whatsapp-video/assets/fonts/OFL.txt`).
