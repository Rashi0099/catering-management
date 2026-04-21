import os

filepath = "/home/rasheed/Documents/catrin_boys_website/catering_project/templates/staff/profile.html"
with open(filepath, "r") as f:
    text = f.read()

# Chunk 1
old1 = """    <!-- Avatar -->
    <div id="avatar-wrap" class="lightbox-trigger"
         style="width:90px; height:90px; border-radius:50%; overflow:hidden; position:relative;
                border:2px solid var(--gold); flex-shrink:0; cursor:pointer;"
         onclick="{% if me.photo %}openPhotoViewer('{{ me.photo.url }}'){% else %}document.getElementById('photo-input').click(){% endif %}" title="Click to view photo">
      {% if me.photo %}
        <img id="avatar-img" src="{{ me.photo.url }}" alt="Profile Photo"
             style="width:100%; height:100%; object-fit:cover; display:block;">
      {% else %}
        <div id="avatar-initials"
             style="width:100%; height:100%; background:linear-gradient(135deg,var(--teal),#1a8070);
                    display:flex; align-items:center; justify-content:center;
                    font-size:2rem; font-weight:700; color:#fff;">
          {{ me.full_name|first|upper }}
        </div>
      {% endif %}
      <!-- Hover overlay — Click to Change -->
      <div id="avatar-overlay" onclick="event.stopPropagation(); document.getElementById('photo-input').click();"
           style="position:absolute;inset:0;background:rgba(0,0,0,0.45);border-radius:50%;
                  display:flex;flex-direction:column;align-items:center;justify-content:center;
                  opacity:0;transition:opacity 0.2s;" title="Change photo">
        <i class="fas fa-camera" style="color:#fff;font-size:1.3rem;"></i>
        <span style="color:#fff;font-size:0.6rem;margin-top:4px;font-weight:600;">CHANGE</span>
      </div>
    </div>"""

new1 = """    <!-- Avatar -->
    <div id="avatar-wrap" class="lightbox-trigger"
         style="width:90px; height:90px; border-radius:50%; overflow:hidden; position:relative;
                border:2px solid var(--gold); flex-shrink:0; cursor:pointer;"
         onclick="handleAvatarClick()" title="Profile Photo">
      {% if me.photo %}
        <img id="avatar-img" src="{{ me.photo.url }}" alt="Profile Photo"
             style="width:100%; height:100%; object-fit:cover; display:block;">
      {% else %}
        <div id="avatar-initials"
             style="width:100%; height:100%; background:linear-gradient(135deg,var(--teal),#1a8070);
                    display:flex; align-items:center; justify-content:center;
                    font-size:2rem; font-weight:700; color:#fff;">
          {{ me.full_name|first|upper }}
        </div>
      {% endif %}
    </div>"""

text = text.replace(old1, new1)

# Chunk 2
old2 = """      <div style="margin-top:8px; display:flex; gap:12px; align-items:center;">
        <label for="photo-input" style="font-size:0.75rem; color:var(--teal); cursor:pointer; margin:0;">
          <i class="fas fa-camera"></i> Change photo
        </label>
        {% if me.photo %}
          <button onclick="confirmRemovePhoto()" type="button"
                  style="background:none;border:none;padding:0;font-size:0.75rem;color:var(--red);cursor:pointer;opacity:0.8;">
            <i class="fas fa-trash-alt" style="font-size:0.7rem;"></i> Remove
          </button>
        {% endif %}
      </div>"""

new2 = ""

text = text.replace(old2, new2)

# Chunk 3
old3 = """/* ── Avatar hover ───────────────────────────────── */
const avatarWrap    = document.getElementById('avatar-wrap');
const avatarOverlay = document.getElementById('avatar-overlay');
avatarWrap.addEventListener('mouseenter', () => avatarOverlay.style.opacity = '1');
avatarWrap.addEventListener('mouseleave', () => avatarOverlay.style.opacity = '0');"""

new3 = """function handleAvatarClick() {
  const img = document.getElementById('avatar-img');
  if (img && img.src && !img.src.includes('avatar-initials')) {
    openPhotoViewer(img.src);
  } else {
    document.getElementById('photo-input').click();
  }
}"""

text = text.replace(old3, new3)

# Chunk 4
old4 = """function openCropModal(input) {
  const file = input.files[0];
  if (!file) return;

  if (file.size > 10 * 1024 * 1024) {
    alert('📷 File too large! Maximum is 10 MB.');
    input.value = '';
    return;
  }

  const reader = new FileReader();
  reader.onload = function(e) {
    const overlay  = document.getElementById('crop-modal-overlay');
    const cropImg  = document.getElementById('crop-image');

    // Reset previous cropper
    if (cropper) { cropper.destroy(); cropper = null; }
    cropImg.src = e.target.result;

    overlay.classList.add('active');
    document.body.style.overflow = 'hidden';

    // Init Cropper.js — circular aspect 1:1
    cropImg.onload = function() {
      cropper = new Cropper(cropImg, {
        aspectRatio: 1,
        viewMode: 1,
        dragMode: 'move',
        autoCropArea: 0.8,
        restore: false,
        guides: false,
        center: true,
        highlight: false,
        cropBoxMovable: false,
        cropBoxResizable: false,
        toggleDragModeOnDblclick: false,
        // Round preview
        ready() {
          const cropBox = this.cropper.getCropBoxData();
          // Make crop circle visible
          document.querySelector('.cropper-view-box').style.borderRadius = '50%';
          document.querySelector('.cropper-face').style.borderRadius = '50%';
        }
      });
    };
  };
  reader.readAsDataURL(file);
}"""

new4 = """function openCropModal(input) {
  const file = input.files[0];
  if (!file) return;

  if (file.size > 10 * 1024 * 1024) {
    alert('📷 File too large! Maximum is 10 MB.');
    input.value = '';
    return;
  }

  closePhotoViewer();

  const reader = new FileReader();
  reader.onload = function(e) {
    initCropperWithSource(e.target.result);
  };
  reader.readAsDataURL(file);
}

function initCropperWithSource(src) {
  const overlay  = document.getElementById('crop-modal-overlay');
  const cropImg  = document.getElementById('crop-image');

  if (cropper) { cropper.destroy(); cropper = null; }
  cropImg.src = src;

  overlay.classList.add('active');
  document.body.style.overflow = 'hidden';

  cropImg.onload = function() {
    cropper = new Cropper(cropImg, {
      aspectRatio: 1,
      viewMode: 1,
      dragMode: 'move',
      autoCropArea: 0.8,
      restore: false,
      guides: false,
      center: true,
      highlight: false,
      cropBoxMovable: false,
      cropBoxResizable: false,
      toggleDragModeOnDblclick: false,
      ready() {
        document.querySelector('.cropper-view-box').style.borderRadius = '50%';
        document.querySelector('.cropper-face').style.borderRadius = '50%';
      }
    });
  };
}

function adjustExistingPhoto() {
  const img = document.getElementById('full-photo');
  if(!img || !img.src) return;
  closePhotoViewer();
  initCropperWithSource(img.src);
}"""

text = text.replace(old4, new4)

# Chunk 5
old5 = """          // Replace contents with new image
          let img = document.getElementById('avatar-img');
          if (!img) {
            wrap.innerHTML = '';
            img = document.createElement('img');
            img.id = 'avatar-img';
            img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
            wrap.appendChild(img);
            // Re-add overlay
            const ov = document.getElementById('avatar-overlay') || (() => {
              const d = document.createElement('div');
              d.id = 'avatar-overlay';
              d.style.cssText = 'position:absolute;inset:0;background:rgba(0,0,0,0.45);border-radius:50%;display:flex;flex-direction:column;align-items:center;justify-content:center;opacity:0;transition:opacity 0.2s;';
              d.innerHTML = `<i class="fas fa-camera" style="color:#fff;font-size:1.3rem;"></i><span style="color:#fff;font-size:0.6rem;margin-top:4px;font-weight:600;">CHANGE</span>`;
              return d;
            })();
            wrap.appendChild(ov);
          }"""

new5 = """          // Replace contents with new image
          let img = document.getElementById('avatar-img');
          if (!img) {
            wrap.innerHTML = '';
            img = document.createElement('img');
            img.id = 'avatar-img';
            img.style.cssText = 'width:100%;height:100%;object-fit:cover;display:block;';
            wrap.appendChild(img);
          }"""

text = text.replace(old5, new5)

# Chunk 6
old6 = """<div id="photo-viewer-overlay" onclick="closePhotoViewer()">
  <img id="full-photo" src="" alt="Full Profile Photo" onclick="event.stopPropagation()">
  <div style="position:absolute; top:25px; right:25px; color:#fff; font-size:2rem; cursor:pointer; width:40px; height:40px; display:flex; align-items:center; justify-content:center; background:rgba(255,255,255,0.1); border-radius:50%;" onclick="closePhotoViewer()">
    <i class="fas fa-times"></i>
  </div>
</div>"""

new6 = """<div id="photo-viewer-overlay" onclick="closePhotoViewer()" style="flex-direction: column;">
  <img id="full-photo" src="" alt="Full Profile Photo" onclick="event.stopPropagation()" style="margin-bottom: 20px;">
  
  <div style="display: flex; gap: 16px; background: rgba(0,0,0,0.6); padding: 12px 20px; border-radius: 20px; backdrop-filter: blur(10px); flex-wrap: wrap; justify-content: center;" onclick="event.stopPropagation()">
    <button onclick="adjustExistingPhoto()" class="btn btn-ghost" style="background:rgba(255,255,255,0.1); border:1px solid rgba(255,255,255,0.2); color:#fff; padding:8px 16px; border-radius:10px; font-weight:600; cursor:pointer; font-size: 0.9rem;"><i class="fas fa-crop-alt" style="margin-right: 6px;"></i> Adjust</button>

    <label for="photo-input" class="btn btn-primary" style="background:var(--teal); color:#fff; padding:8px 16px; border-radius:10px; font-weight:600; cursor:pointer; margin:0; border:none; display:inline-block; font-size: 0.9rem;"><i class="fas fa-camera" style="margin-right: 6px;"></i> Change</label>

    <button onclick="confirmRemovePhoto(); closePhotoViewer();" class="btn" style="background:rgba(231,76,60,0.8); color:#fff; border:none; padding:8px 16px; border-radius:10px; font-weight:600; cursor:pointer; font-size: 0.9rem;"><i class="fas fa-trash-alt" style="margin-right: 6px;"></i> Remove</button>
  </div>

  <div style="position:absolute; top:25px; right:25px; color:#fff; font-size:2rem; cursor:pointer; width:40px; height:40px; display:flex; align-items:center; justify-content:center; background:rgba(255,255,255,0.1); border-radius:50%;" onclick="closePhotoViewer()">
    <i class="fas fa-times"></i>
  </div>
</div>"""

text = text.replace(old6, new6)

with open(filepath, "w") as f:
    f.write(text)

