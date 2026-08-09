# Deploying KKI Store Management System (GitHub + Render + Aiven)

You already have accounts on GitHub, Render, and Aiven, and a running Aiven
MySQL service. Follow these steps in order.

## 1. Push the code to GitHub (using VS Code)

1. Open this folder (`kki_deploy`) in VS Code.
2. Open the built-in terminal (Terminal → New Terminal) and run:
   ```
   git init
   git add .
   git commit -m "Initial commit - KKI Store Management System"
   ```
3. Go to github.com → click "+" → "New repository". Name it e.g.
   `kki-store-system`. Leave it empty (no README/license). Create it.
4. GitHub will show you commands like this - run them in the same terminal:
   ```
   git remote add origin https://github.com/YOUR-USERNAME/kki-store-system.git
   git branch -M main
   git push -u origin main
   ```
5. Refresh the GitHub page - your files should now be there.

## 2. Create the first login account

You need at least one username/password before anyone can sign in.

1. On your computer, open a terminal in the same folder and install the one
   library needed to run the script:
   ```
   pip install pymysql werkzeug
   ```
2. Run:
   ```
   python create_user.py
   ```
3. It will ask for your Aiven Host, Port, User, Password, and Database name
   (find these in the Aiven console → your MySQL service → Overview tab →
   "Connection information").
4. Then it asks for a new login username/password for the app itself (e.g.
   `store` / a password of your choice). This is what you'll type into the
   KKI app's login screen - it's separate from your Aiven password.
5. Repeat this step for each person who needs their own login.

## 3. Deploy on Render

1. Go to render.com → Dashboard → "New +" → "Web Service".
2. Connect your GitHub account if prompted, then select the
   `kki-store-system` repository.
3. Fill in:
   - **Name**: kki-store-system (or anything you like)
   - **Region**: pick one close to you
   - **Branch**: main
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Instance Type**: Free
4. Scroll to **Environment Variables** and add these (values from your Aiven
   Overview tab):
   | Key | Value |
   |---|---|
   | MYSQL_HOST | (from Aiven) |
   | MYSQL_PORT | (from Aiven) |
   | MYSQL_USER | (from Aiven) |
   | MYSQL_PASSWORD | (from Aiven) |
   | MYSQL_DATABASE | (from Aiven) |
   | SECRET_KEY | any random long string, e.g. `kki-9f8e7d6c5b4a-secret` |
   | FLASK_ENV | production |
5. Click **Create Web Service**. Render will build and deploy - this takes a
   few minutes the first time. Watch the "Logs" tab; when it says something
   like "Booting worker" it's live.
6. Render gives you a URL like `https://kki-store-system.onrender.com` -
   that's your app's permanent address. Open it, sign in with the account you
   created in Step 2.

## 4. Day-to-day after this

- **Free tier note**: Render's free web service goes to sleep after ~15 min
  of no visits. The next visit takes 30-60 seconds to wake up - normal, not
  a bug.
- **To update the app later**: edit files in VS Code, then:
  ```
  git add .
  git commit -m "describe your change"
  git push
  ```
  Render automatically redeploys within a minute or two of every push.
- **To add/reset a login**: run `python create_user.py` again from your
  computer any time.
- **To browse your data directly**: open MySQL Workbench, connect using the
  same Aiven Host/Port/User/Password, and you'll see the `users` and
  `app_state` tables (all your app's data lives in `app_state` as one row).
