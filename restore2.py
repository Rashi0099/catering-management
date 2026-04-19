import re

with open('templates/admin/booking_detail.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Budget -> Coat Sizes
old_budget = """        {% if booking.budget %}<div><label>Client Budget</label><div style="color:var(--gold)">₹{{ booking.budget }}</div></div>{% endif %}"""
new_coat_sizes = """        <div><label>Coat Sizes (Assigned)</label>
          <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:2px;">
            {% if coat_counts %}
              {% for size, count in coat_counts.items %}
                <span style="background:var(--surface); border:1px solid var(--border); padding:2px 6px; border-radius:4px; font-size:0.75rem; color:var(--gold); font-weight:600;">{{ size }}: {{ count }}</span>
              {% endfor %}
            {% else %}
              <span style="font-size:0.75rem; color:var(--muted);">None</span>
            {% endif %}
          </div>
        </div>"""
html = html.replace(old_budget, new_coat_sizes)

# 2. Staff Sum
old_quotas = """      <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">
        <div style="font-size:0.75rem;color:var(--muted);margin-bottom:8px;text-transform:uppercase;font-weight:600">Expected Staff Quotas</div>"""
new_quotas = """      <div style="margin-top:14px;padding-top:14px;border-top:1px solid var(--border)">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <div style="font-size:0.75rem;color:var(--muted);text-transform:uppercase;font-weight:600">Expected Staff Quotas</div>
            <div style="font-size:0.75rem;color:#000;background:var(--green);padding:2px 8px;border-radius:12px;font-weight:700;">Total: {{ booking.quota_captain|add:booking.quota_a|add:booking.quota_b|add:booking.quota_c }}</div>
        </div>"""
html = html.replace(old_quotas, new_quotas)


# 3. Add Captain Checklist at end of RIGHT
captain_html = """
    <div class="panel p-captain">
      <div class="panel-header"><div class="panel-title"><i class="fas fa-list-check" style="color:var(--gold); margin-right:6px"></i> Captain Checklist</div></div>
      <style>
        .capt-task-details > summary { list-style: none; outline: none; }
        .capt-task-details > summary::-webkit-details-marker { display: none; }
        .capt-task-details[open] .fa-chevron-down { transform: rotate(180deg) translateY(0) !important; }
        .capt-task-details .fa-chevron-down { transition: transform 0.2s; }
      </style>
      <div style="display:flex; flex-direction:column; gap:10px;">
          {% if captain_tasks %}
              {% for task in captain_tasks %}
              <details class="capt-task-details" style="background:var(--bg); border:1px solid var(--border); border-radius:8px; overflow:hidden;">
                <summary style="display:flex; align-items:flex-start; padding:12px; gap:12px; cursor:{% if task.description %}pointer{% else %}default{% endif %};">
                  <div style="padding-top:2px;">
                    {% if task.is_completed %}
                      <i class="fas fa-check-circle" style="color:#2e7d32; font-size:1.2rem;"></i>
                    {% else %}
                      <i class="far fa-circle" style="color:var(--muted); font-size:1.2rem;"></i>
                    {% endif %}
                  </div>
                  <div style="flex:1;">
                      <div style="font-weight:600; font-size:0.95rem; display:flex; align-items:center; gap:8px; {% if task.is_completed %}text-decoration:line-through; color:var(--muted);{% else %}color:var(--text);{% endif %}">
                        {{ task.task_name }}
                        {% if task.description %}
                          <i class="fas fa-chevron-down" style="font-size:0.75rem; color:var(--gold); transform: translateY(1px);"></i>
                        {% endif %}
                      </div>
                    {% if task.is_completed %}
                      <div style="font-size:0.75rem; color:var(--muted); margin-top:4px;">
                        <i class="fas fa-user-check"></i> Completed by {{ task.completed_by.full_name }}
                      </div>
                    {% endif %}
                  </div>
                </summary>
                {% if task.description %}
                <div style="padding: 0 12px 12px 42px; font-size:0.85rem; color:var(--muted); opacity: 0.9; line-height: 1.4; margin-top:-4px;">
                  • {{ task.description }}
                </div>
                {% endif %}
              </details>
              {% endfor %}
          {% else %}
              <div style="text-align:center; padding:15px; color:var(--muted); font-size:0.9rem; background: var(--bg); border: 1px dashed rgba(212,168,82,0.3); border-radius: 8px; margin:auto;">Tasks generated automatically when Captain opens event dashboard.</div>
          {% endif %}
      </div>
    </div>
"""
html = html.replace('      </form>\n    </div>\n  </div>', f'      </form>\n    </div>\n{captain_html}\n  </div>')


# 4. Modify Classes and Grid
# We want: `<div class="admin-booking-layout">` wrapping everything.
html = html.replace('<div class="responsive-grid cols-2" style="gap:20px">', '<div class="admin-booking-layout">')

# We want to remove the LEFT and RIGHT wrapper divs.
html = html.replace('<!-- LEFT -->\n  <div>', '<!-- LEFT -->')
# We need to remove the `</div>` that closed the LEFT div.
html = re.sub(r'    </div>\n\n\s*<!-- RIGHT -->\n  <div>', '\n  <!-- RIGHT -->', html)
# This will leave the closing `</div>` for RIGHT at the very bottom untouched... wait; 
# The RIGHT div was enclosed in the `admin-booking-layout` div, so if we remove the `</div>` that closed it:
# Actually at the very end of file we have `  </div>\n\n</div>\n{% endblock %}`
# We must remove one `  </div>\n` before the `admin-booking-layout` closing div to match.
html = re.sub(r'  </div>\n\n</div>\n{% endblock %}', '\n</div>\n{% endblock %}', html)

# Add panel classes
html = html.replace('<!-- LEFT -->\n    <div class="panel"', '<!-- LEFT -->\n    <div class="panel p-client"')
html = html.replace('<div class="panel">\n      <div class="panel-header"><div class="panel-title">Assigned Staff</div></div>', '<div class="panel p-staff" style="margin-top:24px;">\n      <div class="panel-header"><div class="panel-title">Assigned Staff</div></div>')
html = html.replace('<div class="panel" style="margin-top:18px">\n      <div class="panel-header" style="display:flex; justify-content:space-between; align-items:center;">\n        <div class="panel-title">Event Attendance', '<div class="panel p-attendance" style="margin-top:24px;">\n      <div class="panel-header" style="display:flex; justify-content:space-between; align-items:center;">\n        <div class="panel-title">Event Attendance')
html = html.replace('<!-- RIGHT -->\n    <div class="panel"', '<!-- RIGHT -->\n    <div class="panel p-update"')

# 5. Inject styles at the end before {% endblock %}
mobile_styles = """
  <style>
    @media (min-width: 901px) {
      .admin-booking-layout {
        display: grid;
        grid-template-columns: minmax(0, 1.8fr) minmax(0, 1.2fr);
        gap: 24px;
        align-items: start;
      }
      .p-client { grid-column: 1; grid-row: 1; }
      
      .p-staff { grid-column: 1; grid-row: 2; margin-top:0 !important; }
      .p-attendance { grid-column: 1; grid-row: 3; margin-top:0 !important; }
      
      .p-update { grid-column: 2; grid-row: 1; }
      .p-captain { grid-column: 2; grid-row: 2; margin-top:0 !important; }
    }
    @media (max-width: 900px) {
      .admin-booking-layout {
        display: flex;
        flex-direction: column;
        gap: 24px;
      }
      .p-client { order: 1; }
      .p-update { order: 2; margin-top:0 !important; margin-bottom:0 !important; }
      .p-captain { order: 3; }
      .p-staff { order: 4; margin-top:0 !important; margin-bottom:0 !important; }
      .p-attendance { order: 5; margin-top:0 !important; }
    }
  </style>
"""
html = html.replace('{% endblock %}', f'{mobile_styles}\n{{% endblock %}}')

with open('templates/admin/booking_detail.html', 'w', encoding='utf-8') as f:
    f.write(html)
