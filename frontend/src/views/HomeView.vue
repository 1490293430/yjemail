<template>
  <div class="home-container">
    <div class="page-header">
      <h1 class="page-title">最新邮件</h1>
      <el-button type="primary" @click="refreshMails" :loading="loading" :icon="Refresh">
        刷新
      </el-button>
    </div>

    <el-table
      v-loading="loading"
      :data="mailRecords"
      style="width: 100%"
      stripe
      border
      highlight-current-row
      @row-click="viewMailContent"
      class="mail-table"
    >
      <el-table-column prop="recipient_email" label="收件邮箱" width="220" show-overflow-tooltip />
      <el-table-column prop="subject" label="主题" min-width="300" show-overflow-tooltip>
        <template #default="scope">
          <div class="subject-cell">
            <span>{{ scope.row.subject || '(无主题)' }}</span>
            <el-tag v-if="scope.row.has_attachments" size="small" type="success" class="attachment-tag">
              附件
            </el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="sender" label="发件人" width="200" show-overflow-tooltip />
      <el-table-column prop="received_time" label="接收时间" width="180">
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
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import dayjs from 'dayjs'
import DOMPurify from 'dompurify'

const loading = ref(false)
const mailRecords = ref([])
const mailContentDialogVisible = ref(false)
const selectedMail = ref(null)

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
