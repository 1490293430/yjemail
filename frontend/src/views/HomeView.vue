<template>
  <div class="home-container">
    <div class="page-header">
      <h1 class="page-title">最新邮件</h1>
      <el-button type="primary" @click="refreshMails" :loading="loading" :icon="Refresh">
        刷新
      </el-button>
    </div>

    <el-table
      ref="mailTableRef"
      v-loading="loading"
      :data="mailRecords"
      style="width: 100%"
      stripe
      border
      highlight-current-row
      @row-click="viewMailContent"
      @header-dragend="handleHeaderDragend"
      class="mail-table"
    >
      <el-table-column prop="recipient_email" label="收件邮箱" :width="columnWidths.recipient_email" resizable show-overflow-tooltip />
      <el-table-column prop="subject" label="主题" :width="columnWidths.subject" resizable show-overflow-tooltip>
        <template #default="scope">
          <div class="subject-cell">
            <span>{{ scope.row.subject || '(无主题)' }}</span>
            <el-tag v-if="scope.row.has_attachments" size="small" type="success" class="attachment-tag">
              附件
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="content" label="内容预览" :min-width="columnWidths.content" resizable>
        <template #default="scope">
          <div class="content-preview">{{ getContentPreview(scope.row) }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="sender" label="发件人" :width="columnWidths.sender" resizable show-overflow-tooltip />
      <el-table-column prop="received_time" label="接收时间" :width="columnWidths.received_time" resizable>
        <template #default="scope">
          <span>{{ formatDate(scope.row.received_time) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="!loading && mailRecords.length === 0" class="empty-state">
      <el-empty description="暂无邮件，请先添加邮箱并收取邮件">
        <el-button type="primary" @click="$router.push('/emails')">去添加邮箱</el-button>
      </el-empty>
    </div>

    <!-- 邮件内容查看对话框 -->
    <el-dialog
      v-model="mailContentDialogVisible"
      :title="selectedMail ? selectedMail.subject : '邮件详情'"
      width="80%"
      top="5vh"
      class="mail-content-dialog"
    >
      <div v-if="selectedMail" class="mail-detail">
        <div class="mail-meta">
          <p><strong>收件邮箱：</strong>{{ selectedMail.recipient_email }}</p>
          <p><strong>发件人：</strong>{{ selectedMail.sender }}</p>
          <p><strong>时间：</strong>{{ formatDate(selectedMail.received_time) }}</p>
        </div>
        <el-divider />
        <div class="mail-content" v-html="sanitizeHtml(getMailContent(selectedMail))"></div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { ElNotification } from 'element-plus'
import dayjs from 'dayjs'
import DOMPurify from 'dompurify'

const loading = ref(false)
const mailRecords = ref([])
const mailContentDialogVisible = ref(false)
const selectedMail = ref(null)
const mailTableRef = ref(null)
let ws = null

// 列宽配置，从 localStorage 读取或使用默认值
const COLUMN_WIDTHS_KEY = 'home_mail_table_column_widths'
const defaultColumnWidths = {
  recipient_email: 200,
  subject: 250,
  content: 400,
  sender: 180,
  received_time: 160
}

const loadColumnWidths = () => {
  try {
    const saved = localStorage.getItem(COLUMN_WIDTHS_KEY)
    if (saved) {
      return { ...defaultColumnWidths, ...JSON.parse(saved) }
    }
  } catch (e) {
    console.error('加载列宽配置失败:', e)
  }
  return { ...defaultColumnWidths }
}

const columnWidths = reactive(loadColumnWidths())

// 列宽拖动结束时保存
const handleHeaderDragend = (newWidth, oldWidth, column) => {
  const prop = column.property
  if (prop && columnWidths[prop] !== undefined) {
    columnWidths[prop] = newWidth
    saveColumnWidths()
  }
}

const saveColumnWidths = () => {
  try {
    localStorage.setItem(COLUMN_WIDTHS_KEY, JSON.stringify(columnWidths))
  } catch (e) {
    console.error('保存列宽配置失败:', e)
  }
}

const fetchLatestMails = async () => {
  loading.value = true
  try {
    const response = await fetch('/api/mail_records/latest', {
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`
      }
    })
    if (response.ok) {
      mailRecords.value = await response.json()
    }
  } catch (error) {
    console.error('获取最新邮件失败:', error)
  } finally {
    loading.value = false
  }
}

const connectWebSocket = () => {
  const token = localStorage.getItem('token')
  if (!token) return
  
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsUrl = `${protocol}//${window.location.host}/ws`
  
  ws = new WebSocket(wsUrl)
  
  ws.onopen = () => {
    console.log('WebSocket 已连接')
    // 发送认证消息
    ws.send(JSON.stringify({
      type: 'authenticate',
      token: token
    }))
  }
  
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      
      if (data.type === 'new_mails') {
        // 收到新邮件，更新列表
        handleNewMails(data.data)
      }
    } catch (error) {
      console.error('解析 WebSocket 消息失败:', error)
    }
  }
  
  ws.onclose = () => {
    console.log('WebSocket 已断开，5秒后重连...')
    setTimeout(connectWebSocket, 5000)
  }
  
  ws.onerror = (error) => {
    console.error('WebSocket 错误:', error)
  }
}

const handleNewMails = (newMails) => {
  if (!newMails || newMails.length === 0) return
  
  let addedCount = 0
  // 将新邮件添加到列表顶部
  for (const mail of newMails) {
    // 检查是否已存在
    const exists = mailRecords.value.some(m => m.id === mail.id)
    if (!exists) {
      mailRecords.value.unshift(mail)
      addedCount++
    }
  }
  
  // 限制列表长度
  if (mailRecords.value.length > 50) {
    mailRecords.value = mailRecords.value.slice(0, 50)
  }
  
  // 显示通知（汇总显示）
  if (addedCount > 0) {
    const firstMail = newMails[0]
    const message = addedCount === 1 
      ? `${firstMail.sender}: ${firstMail.subject}`
      : `收到 ${addedCount} 封新邮件`
    
    ElNotification({
      title: '收到新邮件',
      message: message,
      type: 'success',
      duration: 5000
    })
  }
}

const refreshMails = () => {
  fetchLatestMails()
}

const formatDate = (dateString) => {
  if (!dateString) return '无'
  return dayjs(dateString).format('YYYY-MM-DD HH:mm:ss')
}

const viewMailContent = (row) => {
  selectedMail.value = row
  mailContentDialogVisible.value = true
}

const getMailContent = (mail) => {
  if (!mail) return ''
  if (typeof mail.content === 'object' && mail.content !== null) {
    return mail.content.content || ''
  }
  return mail.content || ''
}

const getContentPreview = (mail) => {
  if (!mail) return ''
  let content = ''
  
  if (typeof mail.content === 'object' && mail.content !== null) {
    content = mail.content.content || mail.content.text || ''
  } else {
    content = mail.content || ''
  }
  
  // 移除 HTML 标签
  content = content.replace(/<[^>]*>/g, ' ')
  // 移除多余空白
  content = content.replace(/\s+/g, ' ').trim()
  // 截取前 200 个字符
  if (content.length > 200) {
    content = content.substring(0, 200) + '...'
  }
  return content || '(无内容)'
}

const sanitizeHtml = (html) => {
  if (!html) return ''
  return DOMPurify.sanitize(html, {
    ALLOWED_TAGS: [
      'a', 'b', 'br', 'div', 'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
      'i', 'img', 'li', 'ol', 'p', 'span', 'strong', 'table', 'tbody',
      'td', 'th', 'thead', 'tr', 'u', 'ul', 'font', 'blockquote', 'hr',
      'pre', 'code'
    ],
    ALLOWED_ATTR: ['href', 'src', 'alt', 'style', 'class', 'target', 'color', 'size']
  })
}

onMounted(() => {
  fetchLatestMails()
  connectWebSocket()
})

onUnmounted(() => {
  if (ws) {
    ws.close()
    ws = null
  }
})
</script>

<style scoped>
.home-container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-title {
  font-size: 1.8rem;
  color: var(--primary-color);
  margin: 0;
}

.mail-table {
  cursor: pointer;
}

.subject-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.attachment-tag {
  flex-shrink: 0;
}

.content-preview {
  color: #666;
  font-size: 13px;
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  word-break: break-all;
  max-height: 2.8em; /* 1.4 * 2 行 */
}

.empty-state {
  padding: 60px 0;
}

.mail-detail {
  max-height: 70vh;
  overflow-y: auto;
}

.mail-meta {
  background: #f5f7fa;
  padding: 15px;
  border-radius: 8px;
}

.mail-meta p {
  margin: 8px 0;
}

.mail-content {
  padding: 15px 0;
  line-height: 1.6;
  word-break: break-word;
}

.mail-content img {
  max-width: 100%;
  height: auto;
}
</style>
