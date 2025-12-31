const startBtn = document.getElementById('startBtn');
const urlInput = document.getElementById('urlInput');
const statusDiv = document.getElementById('status');
const logArea = document.getElementById('logArea');
const commentsTable = document.getElementById('commentsTable').querySelector('tbody');
const commentCountSpan = document.getElementById('commentCount');
const downloadBtn = document.getElementById('downloadBtn');

let ws;
let commentCount = 0;

function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws/crawl`);

    ws.onopen = () => {
        console.log('Connected to WebSocket');
    };

    ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleMessage(message);
    };

    ws.onclose = () => {
        console.log('Disconnected');
        statusDiv.textContent = '连接断开，请刷新页面';
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket Error:', error);
        statusDiv.textContent = '连接错误';
    };
}

function handleMessage(msg) {
    if (msg.type === 'log') {
        const div = document.createElement('div');
        div.textContent = msg.message;
        logArea.appendChild(div);
        logArea.scrollTop = logArea.scrollHeight;
        
        // Check for specific log messages to update status
        if (msg.message.includes('Begin login')) {
            statusDiv.textContent = '需要在浏览器中登录小红书...';
            statusDiv.style.background = '#ffeeba';
        }
    } else if (msg.type === 'comment') {
        addCommentToTable(msg.data);
    } else if (msg.type === 'done') {
        statusDiv.textContent = '抓取完成!';
        statusDiv.style.background = '#d4edda';
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';
        
        if (msg.file_path) {
            downloadBtn.href = `/download?file_path=${encodeURIComponent(msg.file_path)}`;
            downloadBtn.classList.remove('hidden');
        }
    } else if (msg.type === 'error') {
        statusDiv.textContent = msg.message;
        statusDiv.style.background = '#f8d7da';
        statusDiv.style.color = '#721c24';
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';
    }
}

function addCommentToTable(comment) {
    commentCount++;
    commentCountSpan.textContent = commentCount;

    const tr = document.createElement('tr');
    
    // User info
    const userCell = document.createElement('td');
    userCell.className = 'user-cell';
    
    // Handle avatar (if available in user_info or user)
    const userInfo = comment.user_info || {};
    const avatarUrl = userInfo.image || '';
    const nickname = userInfo.nickname || '未知用户';
    
    if (avatarUrl) {
        const img = document.createElement('img');
        img.src = avatarUrl;
        img.className = 'avatar';
        userCell.appendChild(img);
    }
    const nameSpan = document.createElement('span');
    nameSpan.textContent = nickname;
    userCell.appendChild(nameSpan);
    
    tr.appendChild(userCell);
    
    // Content
    const contentCell = document.createElement('td');
    contentCell.textContent = comment.content;
    tr.appendChild(contentCell);
    
    // Likes
    const likeCell = document.createElement('td');
    likeCell.textContent = comment.like_count || 0;
    tr.appendChild(likeCell);
    
    // Time
    const timeCell = document.createElement('td');
    // Format timestamp if needed
    let timeStr = comment.create_time;
    if (timeStr) {
         try {
            // Check if it's timestamp (number)
            if (!isNaN(timeStr)) {
                 let ts = parseInt(timeStr);
                 // if timestamp is in seconds (10 digits), convert to ms
                 if (String(ts).length === 10) ts *= 1000;
                 timeStr = new Date(ts).toLocaleString();
            }
         } catch(e) {}
    }
    timeCell.textContent = timeStr;
    tr.appendChild(timeCell);

    // Prepend to show newest first
    commentsTable.insertBefore(tr, commentsTable.firstChild);
}

startBtn.addEventListener('click', () => {
    const url = urlInput.value.trim();
    if (!url) {
        alert('请输入 URL');
        return;
    }

    // Reset UI
    logArea.innerHTML = '';
    commentsTable.innerHTML = '';
    commentCount = 0;
    commentCountSpan.textContent = '0';
    downloadBtn.classList.add('hidden');
    statusDiv.textContent = '正在初始化...';
    statusDiv.style.background = '#eef';
    
    startBtn.disabled = true;
    startBtn.textContent = '抓取中...';

    // Send start command
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: 'start',
            url: url
        }));
    } else {
        alert('WebSocket 未连接，请刷新页面');
        startBtn.disabled = false;
        startBtn.textContent = '开始抓取';
    }
});

// Initial connect
connectWebSocket();
