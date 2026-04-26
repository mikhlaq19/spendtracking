---
description: Create a single dummy user in the database
allowed-tools: Read, Bash(python3:*)
---

Read `database/db.py` to understand the users table schema and the `get_db()` helper.

Then write and run a Python script using Bash that:

## 1. Generate User

Generate a realistic random Pakistani user using your own knowledge of common Pakistani names across regions:

- **Name**: a realistic Pakistani first + last name  
- **Email**: derived from the name with a random 2–3 digit number suffix  
  - Example: `rahul.sharma91@gmail.com`  
- **Password**: `"password123"` hashed with `werkzeug.security.generate_password_hash`  
- **created_at**: current datetime  

## 2. Ensure Email Uniqueness

- Check if the generated email already exists in the `users` table  
- If it exists, regenerate until a unique email is found  

## 3. Insert into Database

- Insert the user into the database  
- Use the same `get_db()` pattern found in `db.py`  

## 4. Output

Print confirmation:

- `id`
- `name`
- `email`