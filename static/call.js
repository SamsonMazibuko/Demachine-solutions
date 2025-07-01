// static/call.js
let socket = io();
let localStream = null;
let peerConnection = null;
let currentRoom = null;
let callTimeout = null;
let currentCallId = null;

// ICE servers for WebRTC
const iceServers = {
    iceServers: [
        { urls: 'stun:stun.l.google.com:19302' }
    ]
};

// Bootstrap modal instance
let callModal = null;
let incomingCallModal = null;
let pendingCallData = null;

let ringtoneAudio = new Audio('/static/call_ringtone.mp3');
ringtoneAudio.loop = true;

function playRingtoneAndVibrate() {
    try { ringtoneAudio.play(); } catch (e) {}
    if (navigator.vibrate) navigator.vibrate([500, 300, 500, 300, 500]);
}

function stopRingtoneAndVibrate() {
    ringtoneAudio.pause();
    ringtoneAudio.currentTime = 0;
    if (navigator.vibrate) navigator.vibrate(0);
}

function showCallModal(status) {
    if (!callModal) {
        callModal = new bootstrap.Modal(document.getElementById('callModal'));
    }
    document.getElementById('callStatus').innerText = status || 'Connecting...';
    callModal.show();
    addMinimizeButtonToCallModal();
    hideCallBar();
}

function hideCallModal() {
    if (callModal) callModal.hide();
    if (localStream && peerConnection) {
        showCallBar('In call...');
    }
}

function setCallStatus(status) {
    document.getElementById('callStatus').innerText = status;
}

function showIncomingCallModal(data) {
    if (!incomingCallModal) {
        incomingCallModal = new bootstrap.Modal(document.getElementById('incomingCallModal'));
    }
    pendingCallData = data;
    document.getElementById('incomingCallStatus').innerText = 'A user is calling you. Would you like to accept?';
    incomingCallModal.show();
    playRingtoneAndVibrate();
}

function hideIncomingCallModal() {
    if (incomingCallModal) incomingCallModal.hide();
    pendingCallData = null;
    stopRingtoneAndVibrate();
}

function acceptCall() {
    if (pendingCallData) {
        currentCallId = pendingCallData.call_id;
        socket.emit('call_response', {
            from_admin_id: window.currentUserId,
            from_admin_sid: socket.id,
            to_user_id: pendingCallData.from_user_id,
            accepted: true,
            call_id: currentCallId
        });
        setCallStatus('Connecting...');
        startCall(currentCallId);
        hideIncomingCallModal();
        stopRingtoneAndVibrate();
    }
}

function rejectCall() {
    if (pendingCallData) {
        socket.emit('call_response', { from_admin_id: window.currentUserId, to_user_id: pendingCallData.from_user_id, accepted: false });
        hideIncomingCallModal();
        hideCallModal();
        stopRingtoneAndVibrate();
    }
}

// Call request (user to admin)
function callAdmin() {
    currentCallId = 'call_' + window.currentUserId + '_' + Date.now();
    showCallModal('Calling admin...');
    socket.emit('call_request', { from_user_id: window.currentUserId, to_role: 'admin', call_id: currentCallId });
    // Start missed call timer (30 seconds)
    if (callTimeout) clearTimeout(callTimeout);
    callTimeout = setTimeout(() => {
        setCallStatus('Missed call. No admin answered.');
        setTimeout(hideCallModal, 2000);
    }, 30000);
    // Always start call for user
    console.log('User is starting call, currentUserRole:', window.currentUserRole, 'currentCallId:', currentCallId);
    startCall(currentCallId);
}

// Listen for incoming call (admin side)
socket.on('incoming_call', function(data) {
    if (window.currentUserRole === 'admin') {
        showIncomingCallModal(data);
    }
});

// Listen for call response (user side)
socket.on('call_response', function(data) {
    console.log('User received call_response:', data);
    if (callTimeout) clearTimeout(callTimeout);
    if (data.accepted) {
        console.log('Call accepted by admin');
        setCallStatus('Connecting...');
        // Do NOT call startCall here for user
    } else {
        console.log('Call rejected by admin');
        setCallStatus('Admin rejected your call.');
        setTimeout(hideCallModal, 2000);
    }
});

// Show a notification if no admin is online
socket.on('no_admin_online', function() {
    if (callTimeout) clearTimeout(callTimeout);
    setCallStatus('No admin is online. Please try again later.');
    showCallModal('No admin is online. Please try again later.');
    setTimeout(hideCallModal, 2500);
});

// Start WebRTC call
function startCall(callId) {
    console.log('Starting call with callId:', callId);
    currentRoom = callId;
    socket.emit('join_room', { room: currentRoom });
    const localVideo = document.getElementById('localVideo');
    if (localVideo) {
        localVideo.style.display = 'block';
        localVideo.width = 160;
        localVideo.height = 120;
    }
    navigator.mediaDevices.getUserMedia({ audio: true, video: true })
        .then(stream => {
            console.log('Got user media stream', stream);
            localStream = stream;
            if (localVideo) {
                localVideo.srcObject = localStream;
                localVideo.style.display = 'block';
            } else {
                console.error('localVideo element not found in DOM');
            }
            peerConnection = new RTCPeerConnection(iceServers);
            localStream.getTracks().forEach(track => peerConnection.addTrack(track, localStream));
            peerConnection.onicecandidate = event => {
                if (event.candidate) {
                    socket.emit('signal', { room: currentRoom, signal_data: { type: 'candidate', candidate: event.candidate } });
                }
            };
            peerConnection.ontrack = event => {
                console.log('Received remote stream');
                let remoteVideo = document.getElementById('remoteVideo');
                if (remoteVideo) {
                    remoteVideo.srcObject = event.streams[0];
                    remoteVideo.style.display = 'block';
                }
            };
            if (window.currentUserRole !== 'admin') {
                console.log('User creating offer...');
                peerConnection.createOffer().then(offer => {
                    peerConnection.setLocalDescription(offer);
                    socket.emit('signal', { room: currentRoom, signal_data: { type: 'offer', offer: offer } });
                });
            }
            setCallStatus('In call');
            showCallModal('In call');
        })
        .catch(err => {
            console.error('Error getting user media:', err);
            alert('Could not access camera/mic: ' + err.message);
            setCallStatus('Could not access camera/mic: ' + err.message);
            setTimeout(hideCallModal, 2000);
        });
}

// End call logic
function endCall() {
    if (peerConnection) {
        peerConnection.close();
        peerConnection = null;
    }
    if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
    }
    setCallStatus('Call ended');
    setTimeout(hideCallModal, 1000);
    hideCallBar();
}

// Handle signaling
socket.on('signal', function(data) {
    console.log('Received signal:', data);
    if (!peerConnection) {
        console.warn('No peerConnection when signal received');
        return;
    }
    if (data.type === 'offer') {
        console.log('Received offer:', data.offer);
        peerConnection.setRemoteDescription(new RTCSessionDescription(data.offer)).then(() => {
            console.log('Set remote description (offer)');
            peerConnection.createAnswer().then(answer => {
                peerConnection.setLocalDescription(answer);
                console.log('Created and set local description (answer)', answer);
                socket.emit('signal', { room: currentRoom, signal_data: { type: 'answer', answer: answer } });
            });
        });
    } else if (data.type === 'answer') {
        console.log('Received answer:', data.answer);
        peerConnection.setRemoteDescription(new RTCSessionDescription(data.answer)).then(() => {
            console.log('Set remote description (answer)');
        });
    } else if (data.type === 'candidate') {
        console.log('Received ICE candidate:', data.candidate);
        peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
    }
});

// Utility: Attach local stream to video element
function attachLocalVideo(videoElementId) {
    let video = document.getElementById(videoElementId);
    if (video && localStream) {
        video.srcObject = localStream;
    }
}

socket.on('call_answered', function(data) {
    // If this admin is not the one who answered, close the incoming call modal and stop notifications
    if (window.currentUserId != data.from_admin_id) {
        hideIncomingCallModal();
    }
});

function showCallBar(status) {
    const callBar = document.getElementById('callBar');
    const callBarStatus = document.getElementById('callBarStatus');
    if (callBar && callBarStatus) {
        callBarStatus.innerText = status || 'In call...';
        callBar.style.display = 'flex';
    }
}

function hideCallBar() {
    const callBar = document.getElementById('callBar');
    if (callBar) callBar.style.display = 'none';
}

function restoreCallModal() {
    showCallModal('In call');
    hideCallBar();
}

// Add a Minimize button to the call modal
function addMinimizeButtonToCallModal() {
    const modalHeader = document.querySelector('#callModal .modal-header');
    if (modalHeader && !document.getElementById('minimizeCallBtn')) {
        const btn = document.createElement('button');
        btn.id = 'minimizeCallBtn';
        btn.className = 'btn btn-sm btn-outline-secondary';
        btn.innerHTML = '<i class="bi bi-dash"></i>';
        btn.style.marginRight = '8px';
        btn.onclick = function() {
            hideCallModal();
            showCallBar('In call...');
        };
        modalHeader.insertBefore(btn, modalHeader.firstChild);
    }
}

// Patch endCall to hide call bar
const _origEndCall = endCall;
endCall = function() {
    hideCallBar();
    _origEndCall();
}; 