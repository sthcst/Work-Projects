import os
import random
import argparse
from datetime import datetime, timedelta

FIRST = [
    'Emily', 'John', 'Carlos', 'Aisha', 'Wei', 'Sven', 'Fatima', 'Olga', 'Liam', 'Noah',
    'Emma', 'Olivia', 'Sophia', 'Isabella', 'Mia', 'Lucas', 'Mateo', 'Hiro', 'Priya', 'Amir'
]

LAST = [
    'Smith', 'Johnson', 'Garcia', 'Martinez', 'Khan', 'Wang', 'Nguyen', 'Patel', 'Brown', 'Davis',
    'Miller', 'Wilson', 'Anderson', 'Taylor', 'Thomas', 'Moore', 'Martin', 'Lee', 'Perez', 'Lopez'
]

STREET_NAMES = [
    'Oak', 'Maple', 'Pine', 'Cedar', 'Elm', 'Washington', 'Lake', 'Hill', 'Main', 'Broadway',
    'King', 'Queen', 'Victoria', 'George', 'Church', 'High', 'Station', 'Market', 'Garden', 'River'
]

STREET_TYPES = ['St', 'Ave', 'Rd', 'Blvd', 'Ln', 'Dr', 'Pl', 'Court', 'Terrace']

CITIES = [
    ('New York', 'NY', 'US'), ('Los Angeles', 'CA', 'US'), ('Chicago', 'IL', 'US'),
    ('Houston', 'TX', 'US'), ('London', '', 'GB'), ('Toronto', 'ON', 'CA'), ('Sydney', 'NSW', 'AU'),
    ('Auckland', '', 'NZ'), ('Berlin', '', 'DE'), ('Paris', '', 'FR')
]

TEMPLATES = [
    'plain', 'json', 'yaml', 'random', 'form', 'signature'
]


def random_email(first, last):
    domains = ['example.com', 'mail.com', 'test.org', 'example.org', 'company.co']
    return f"{first.lower()}.{last.lower()}@{random.choice(domains)}"


def random_phone(country='US'):
    if country == 'US':
        return f"({random.randint(200,999)}) {random.randint(200,999)}-{random.randint(1000,9999)}"
    if country == 'GB':
        return f"+44 7{random.randint(100000000,999999999)}"
    return f"+{random.randint(1,99)} {random.randint(100000000,999999999)}"


def random_ssn():
    # sometimes formatted, sometimes raw
    if random.random() < 0.7:
        return f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"
    else:
        return f"{random.randint(100000000,999999999)}"


def random_dob():
    start = datetime(1940, 1, 1)
    end = datetime(2005, 12, 31)
    d = start + timedelta(days=random.randint(0, (end - start).days))
    # return various formats
    if random.random() < 0.5:
        return d.strftime('%m/%d/%Y')
    else:
        return d.strftime('%B %d, %Y')


def random_address(country_hint=None):
    # create either US-style or international variants
    city, state, country = random.choice(CITIES) if country_hint is None else random.choice([c for c in CITIES if c[2] == country_hint] or CITIES)
    num = random.randint(10, 9999)
    street = f"{num} {random.choice(STREET_NAMES)} {random.choice(STREET_TYPES)}"
    # choose sometimes to include apartment
    if random.random() < 0.2:
        street = f"{street}, Apt {random.randint(1,999)}"
    if country == 'US' or country == 'CA':
        return f"{street}, {city}, {state}"
    if country == 'GB':
        return f"{num} {random.choice(STREET_NAMES)} {random.choice(['Road','Street','Way'])}, {city}, UK"
    return f"{street}, {city}, {country}"


def make_email(i, long=False, paragraphs=10):
    first = random.choice(FIRST)
    last = random.choice(LAST)
    name = f"{first} {last}"
    email = random_email(first, last)
    city, state, country = random.choice(CITIES)
    addr = random_address(country_hint=country)
    phone = random_phone(country='US' if country == 'US' else 'INT')
    ssn = random_ssn()
    dob = random_dob()

    tpl = random.choice(TEMPLATES)

    subject = random.choice(['Verification', 'Your Details', 'Meeting', 'Important', 'Invoice'])

    if tpl == 'plain':
        body = f"Subject: {subject}\n\nHello {first},\n\nYour details:\nEmail: {email}\nPhone: {phone}\nSSN: {ssn}\nAddress: {addr}\nDOB: {dob}\n\nThanks,\n{first}\n"
    elif tpl == 'json':
        body = '{\n  "subject": "%s",\n  "name": "%s",\n  "email": "%s",\n  "phone": "%s",\n  "ssn": "%s",\n  "address": "%s",\n  "date": "%s"\n}' % (subject, name, email, phone, ssn, addr, dob)
    elif tpl == 'yaml':
        body = 'subject: %s\nname: %s\nemail: %s\nphone: %s\nssn: %s\naddress: %s\ndate: %s\n' % (subject, name, email, phone, ssn, addr, dob)
    elif tpl == 'form':
        body = f"From: {name} <{email}>\nTo: records@company.co\nDate: {dob}\nSubject: {subject}\n\nPlease update the record:\nName: {name}\nAddress: {addr}\nPhone: {phone}\nSSN: {ssn}\n"
    elif tpl == 'signature':
        body = f"Hi there,\n\nThis is a short message.\n\nBest,\n{first} {last}\n{email}\n{phone}\n{addr}\n"
    else:
        # random blob with PII sprinkled
        lines = []
        lines.append(f"User: {name}")
        if random.random() < 0.8:
            lines.append(f"Contact: {email} | {phone}")
        if random.random() < 0.6:
            lines.append(f"SSN: {ssn}")
        if random.random() < 0.6:
            lines.append(f"DOB: {dob}")
        if random.random() < 0.7:
            lines.append(f"Address: {addr}")
        body = '\n'.join(lines) + '\n'

    # Add some random noise and variations
    if random.random() < 0.1:
        # include PO Box example
        body += f"PO Box {random.randint(100,9999)}\n"
    if random.random() < 0.05:
        # include non-US formatted address
        body += f"International: {random_address(country_hint='GB')}\n"

    # If long message requested, build a long body with many paragraphs and sprinkled PII
    if long:
        paras = []
        for p in range(max(1, paragraphs)):
            # build a paragraph with 4-12 sentences
            sents = []
            for _ in range(random.randint(4, 12)):
                # choose sentence templates
                t = random.choice([
                    'This is a follow-up regarding your recent submission.',
                    'Please confirm the details below when you have a moment.',
                    'We need to verify the following information to proceed.',
                    'Our records show the following entry for your account.',
                    'If any of the data is incorrect, reply to this message with updates.'
                ])
                # occasionally inject PII items into sentences
                if random.random() < 0.25:
                    choice = random.choice(['email', 'phone', 'ssn', 'addr', 'dob', 'name'])
                    if choice == 'email':
                        t += f' Contact: {email}.'
                    elif choice == 'phone':
                        t += f' Reach me at {phone}.'
                    elif choice == 'ssn':
                        t += f' SSN on file: {ssn}.'
                    elif choice == 'addr':
                        t += f' Address listed: {addr}.'
                    elif choice == 'dob':
                        t += f' DOB: {dob}.'
                    elif choice == 'name':
                        t += f' Name on record: {name}.'

                sents.append(t)

            para = ' '.join(sents)
            paras.append(para)

        long_body = '\n\n'.join(paras)
        # Prepend subject and greeting
        header = f"Subject: {subject}\n\nHello {first},\n\n"
        body = header + long_body + f"\n\nThanks,\n{first} {last}\n"

    # Prepend a From line sometimes (mimic mbox boundaries)
    if random.random() < 0.3:
        header = f"From {email} {datetime.utcnow().ctime()}\n"
        return header + body

    return body


def main():
    parser = argparse.ArgumentParser(description='Generate synthetic email files for redaction testing')
    parser.add_argument('--count', '-n', type=int, default=300, help='Number of emails to generate')
    parser.add_argument('--outdir', '-o', type=str, default='emails_folder/Spam/test_emails/generated_emails_bulk', help='Output folder')
    parser.add_argument('--seed', type=int, default=None, help='Random seed')
    parser.add_argument('--long', action='store_true', help='Generate long emails with many paragraphs and PII')
    parser.add_argument('--paragraphs', type=int, default=10, help='Number of paragraphs for long emails')
    args = parser.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    os.makedirs(args.outdir, exist_ok=True)

    for i in range(1, args.count + 1):
        content = make_email(i, long=args.long, paragraphs=args.paragraphs)
        filename = os.path.join(args.outdir, f'email_{i}.txt')
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)

    print(f"Wrote {args.count} emails to {args.outdir}")


if __name__ == '__main__':
    main()
