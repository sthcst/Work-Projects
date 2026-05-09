#!/usr/bin/env python3
"""Generate 100000 diverse test emails with realistic PII."""

import random
import os
from pathlib import Path

random.seed(42)

# Output directory
OUTPUT_DIR = Path('test_emails_100000')
OUTPUT_DIR.mkdir(exist_ok=True)

# Name components for generating realistic names
first_names = [
    'John', 'Jane', 'Michael', 'Sarah', 'David', 'Emily', 'Robert', 'Jessica',
    'James', 'Ashley', 'William', 'Rachel', 'Richard', 'Lauren', 'Joseph', 'Amanda',
    'Charles', 'Megan', 'Christopher', 'Stephanie', 'Daniel', 'Katherine', 'Matthew', 'Jennifer',
    'Anthony', 'Rebecca', 'Mark', 'Angela', 'Donald', 'Lisa', 'Steven', 'Kimberly',
    'Paul', 'Maria', 'Andrew', 'Michelle', 'Joshua', 'Cynthia', 'Kenneth', 'Kathleen',
    'Kevin', 'Shirley', 'Brian', 'Angela', 'George', 'Helen', 'Edward', 'Anna',
    'Ronald', 'Brenda', 'Timothy', 'Pamela', 'Jason', 'Nicole', 'Jeffrey', 'Emma',
    'Ryan', 'Samantha', 'Jacob', 'Katherine', 'Gary', 'Christine', 'Nicholas', 'Deborah',
]

last_names = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller', 'Davis',
    'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez', 'Wilson', 'Anderson', 'Thomas',
    'Taylor', 'Moore', 'Jackson', 'Martin', 'Lee', 'Perez', 'Thompson', 'White',
    'Harris', 'Sanchez', 'Clark', 'Ramirez', 'Lewis', 'Robinson', 'Young', 'Walker',
    'Hall', 'Alvarado', 'Nelson', 'Carter', 'Roberts', 'Phillips', 'Campbell', 'Parker',
    'Evans', 'Edwards', 'Collins', 'Reeves', 'Stewart', 'Morris', 'Rogers', 'Morgan',
    'Peterson', 'Cooper', 'Reed', 'Bell', 'Gomez', 'Murillo', 'Dominguez', 'Reyes',
    'Ortiz', 'Jimenez', 'Delgado', 'Flores', 'Romero', 'Guerrero', 'Serrano', 'Nunez',
]

domains = ['gmail.com', 'yahoo.com', 'outlook.com', 'company.com', 'example.com', 'mail.com', 'business.net', 'work.org']
cities = ['New York', 'Los Angeles', 'Chicago', 'Houston', 'Phoenix', 'Philadelphia', 'San Antonio', 'San Diego',
          'Dallas', 'San Jose', 'Austin', 'Jacksonville', 'Boston', 'Denver', 'Seattle', 'Washington']
states = ['NY', 'CA', 'IL', 'TX', 'AZ', 'PA', 'TX', 'CA', 'TX', 'CA', 'TX', 'FL', 'MA', 'CO', 'WA', 'DC',
          'FL', 'GA', 'NC', 'OH', 'MI', 'NJ', 'VA', 'WA', 'AZ', 'MA', 'TN', 'MO', 'MD', 'WI']
streets = ['Main', 'Oak', 'Elm', 'Pine', 'Maple', 'Cedar', 'Birch', 'Park', 'Spring', 'Summer', 'North', 'South', 
           'East', 'West', 'First', 'Second', 'Third', 'Fourth', 'Fifth', 'Sixth']

email_templates = [
    # Business email
    """Subject: Meeting Request - {project}

Hi {name},

I hope this email finds you well. I wanted to reach out regarding the {project} initiative.

Your contact information:
Email: {email}
Phone: {phone}
Employee ID: {ssn}

Please let me know your availability for next week.

Best regards,
{sender}""",

    # Support ticket
    """SUPPORT TICKET #{ticket}

Customer: {name}
Email: {email}
Phone: {phone}
Account: {ssn}

Issue Description: Technical problem reported
DOB on file: {dob}
Address: {address}, {city}, {state}

Status: OPEN""",

    # Invoice/Receipt
    """INVOICE {invoice_num}

Bill To:
Name: {name}
Email: {email}
Phone: {phone}
SSN: {ssn}

Address: {address}
{city}, {state}

Date of Birth: {dob}

Amount Due: ${amount}""",

    # Narrative report
    """INCIDENT REPORT

Reported By: {name}
Contact Email: {email}
Contact Phone: {phone}
ID/SSN: {ssn}
Residence: {address}, {city}, {state}
Birth Date: {dob}

Description: Security incident investigation in progress.
Status: PENDING""",

    # CSV format
    """name,email,phone,ssn,dob,address,city,state
{name},{email},{phone},{ssn},{dob},"{address}",{city},{state}""",

    # YAML format
    """contact:
  name: {name}
  email: {email}
  phone: {phone}
  ssn: {ssn}
  dob: {dob}
  address: {address}
  city: {city}
  state: {state}""",

    # JSON format
    """{{
  "contact": {{
    "name": "{name}",
    "email": "{email}",
    "phone": "{phone}",
    "ssn": "{ssn}",
    "dob": "{dob}",
    "address": "{address}",
    "city": "{city}",
    "state": "{state}"
  }}
}}""",

    # Mixed narrative
    """CUSTOMER PROFILE:
{name} ({email}) - Phone: {phone}
SSN: {ssn} | DOB: {dob}
Lives at: {address}, {city}, {state}

Status: Active customer""",

    # Informal chat
    """Hey {name}!

Got your info: {email} and {phone}. 
Your SSN is {ssn}, DOB is {dob}.
Address on file: {address}, {city}, {state}

Let me know if you need anything!""",

    # Form data
    """REGISTRATION FORM

Full Name: {name}
Email Address: {email}
Phone Number: {phone}
Social Security Number: {ssn}
Date of Birth: {dob}
Street Address: {address}
City: {city}
State: {state}""",
]

def generate_phone():
    """Generate phone number in various formats."""
    formats = [
        lambda: f"{random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}",
        lambda: f"({random.randint(200, 999)}) {random.randint(200, 999)}-{random.randint(1000, 9999)}",
        lambda: f"{random.randint(200, 999)} {random.randint(200, 999)} {random.randint(1000, 9999)}",
        lambda: f"+1 {random.randint(200, 999)}-{random.randint(200, 999)}-{random.randint(1000, 9999)}",
    ]
    return random.choice(formats)()

def generate_ssn():
    """Generate SSN in various formats."""
    ssn_base = f"{random.randint(1, 999):03d}{random.randint(1, 99):02d}{random.randint(1000, 9999):04d}"
    formats = [
        lambda s: f"{s[:3]}-{s[3:5]}-{s[5:]}",  # dashed
        lambda s: f"{s[:3]} {s[3:5]} {s[5:]}",  # space-separated
        lambda s: s,  # unseparated
    ]
    return random.choice(formats)(ssn_base)

def generate_dob():
    """Generate date of birth in various formats."""
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    year = random.randint(1950, 2005)
    formats = [
        f"{month:02d}/{day:02d}/{year}",
        f"{month}/{day}/{year}",
        f"{month:02d}-{day:02d}-{year}",
        f"{day:02d}/{month:02d}/{year}",
    ]
    return random.choice(formats)

def generate_address():
    """Generate street address."""
    street_num = random.randint(10, 9999)
    street_name = random.choice(streets)
    street_type = random.choice(['St', 'Ave', 'Rd', 'Ln', 'Dr', 'Blvd', 'Way', 'Court'])
    return f"{street_num} {street_name} {street_type}"

print(f"Generating 100000 test emails with diverse PII...")

for email_idx in range(1, 100001):
    name = f"{random.choice(first_names)} {random.choice(last_names)}"
    email = f"{name.lower().replace(' ', '.')}{random.randint(1, 9999)}@{random.choice(domains)}"
    phone = generate_phone()
    ssn = generate_ssn()
    dob = generate_dob()
    address = generate_address()
    city = random.choice(cities)
    state = random.choice(states)
    sender = f"{random.choice(first_names)} {random.choice(last_names)}"
    project = random.choice(['Q2 Initiative', 'Project Alpha', 'Beta Release', 'Operations Review', 'Audit'])
    ticket = random.randint(10000, 99999)
    invoice_num = random.randint(100000, 999999)
    amount = random.randint(100, 10000)
    
    template = random.choice(email_templates)
    email_content = template.format(
        name=name,
        email=email,
        phone=phone,
        ssn=ssn,
        dob=dob,
        address=address,
        city=city,
        state=state,
        sender=sender,
        project=project,
        ticket=ticket,
        invoice_num=invoice_num,
        amount=amount,
    )
    
    # Write to file
    output_file = OUTPUT_DIR / f"email_{email_idx:06d}.txt"
    output_file.write_text(email_content, encoding='utf-8')
    
    if email_idx % 10000 == 0:
        print(f"  Generated {email_idx}/100000 emails...")

print(f"\n✅ Successfully generated 100000 test emails in {OUTPUT_DIR}/")
print(f"Total files created: {len(list(OUTPUT_DIR.glob('email_*.txt')))}")
