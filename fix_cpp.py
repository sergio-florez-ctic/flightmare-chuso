import re
filepath = '/home/flightmare/flightlib/src/envs/quadrotor_env/quadrotor_env.cpp'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix isTerminalState
content = re.sub(r'if \(quad_state_\.x\(QS::POSZ\) >= 2\.0\) \{', 'if (quad_state_.x(QS::POSZ) <= 0.0) {', content)

# Fix start altitude
content = content.replace('quad_state_.x(QS::POSZ) = -10.0;', 'quad_state_.x(QS::POSZ) = 10.0;')

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)
