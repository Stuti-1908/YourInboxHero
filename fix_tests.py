import os, glob, re
for root, _, files in os.walk('tests'):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, 'r') as file:
                content = file.read()
            # Replace Debtor( with Debtor(user_id='test-id', 
            new_content = re.sub(r'Debtor\(', r"Debtor(user_id='test-id', ", content)
            if new_content != content:
                with open(path, 'w') as file:
                    file.write(new_content)
                print('Updated', path)
