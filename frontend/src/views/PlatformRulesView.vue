<template>
  <div class="page-container">
    <div class="rules-container">
      <el-card class="rules-card shadow">
        <template #header>
          <div class="card-header flex-between">
            <h2 class="page-title">平台识别规则</h2>
            <el-button type="primary" @click="showAddDialog" :icon="Plus">
              添加规则
            </el-button>
          </div>
        </template>

        <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
          <template #title>
            当收到新邮件时，系统会自动匹配规则并标记对应平台。支持正则表达式或简单文本匹配。
          </template>
        </el-alert>

        <el-table
          v-loading="loading"
          :data="rules"
          style="width: 100%"
          stripe
          border
        >
          <el-table-column prop="platform_name" label="平台名称" width="150" />
          <el-table-column prop="sender_pattern" label="发件人匹配" min-width="200">
            <template #default="scope">
              <code v-if="scope.row.sender_pattern">{{ scope.row.sender_pattern }}</code>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="subject_pattern" label="主题匹配" min-width="200">
            <template #default="scope">
              <code v-if="scope.row.subject_pattern">{{ scope.row.subject_pattern }}</code>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="content_pattern" label="内容匹配" min-width="200">
            <template #default="scope">
              <code v-if="scope.row.content_pattern">{{ scope.row.content_pattern }}</code>
              <span v-else class="text-muted">-</span>
            </template>
          </el-table-column>
          <el-table-column prop="is_enabled" label="状态" width="100">
            <template #default="scope">
              <el-switch
                v-model="scope.row.is_enabled"
                :active-value="1"
                :inactive-value="0"
                @change="toggleRule(scope.row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="scope">
              <el-button type="primary" size="small" @click="editRule(scope.row)">编辑</el-button>
              <el-button type="danger" size="small" @click="deleteRule(scope.row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div v-if="!loading && rules.length === 0" class="empty-state">
          <el-empty description="暂无规则，点击上方按钮添加">
            <el-button type="primary" @click="showAddDialog">添加规则</el-button>
          </el-empty>
        </div>
      </el-card>

      <!-- 预设规则卡片 -->
      <el-card class="preset-card shadow" style="margin-top: 20px;">
        <template #header>
          <h3>常用平台预设</h3>
        </template>
        <div class="preset-list">
          <el-button
            v-for="preset in presetRules"
            :key="preset.platform"
            size="small"
            @click="addPresetRule(preset)"
          >
            + {{ preset.platform }}
          </el-button>
        </div>
      </el-card>
    </div>

    <!-- 添加/编辑规则对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEditing ? '编辑规则' : '添加规则'"
      width="500px"
      @close="resetForm"
    >
      <el-form :model="form" :rules="formRules" ref="formRef" label-width="100px">
        <el-form-item label="平台名称" prop="platform_name">
          <el-input v-model="form.platform_name" placeholder="如: MoreLogin" />
        </el-form-item>
        <el-form-item label="发件人匹配" prop="sender_pattern">
          <el-input v-model="form.sender_pattern" placeholder="如: morelogin 或 @morelogin.com" />
          <div class="form-tip">匹配发件人地址，支持正则表达式</div>
        </el-form-item>
        <el-form-item label="主题匹配" prop="subject_pattern">
          <el-input v-model="form.subject_pattern" placeholder="如: 注册成功|账户.*注册" />
          <div class="form-tip">匹配邮件主题，支持正则表达式</div>
        </el-form-item>
        <el-form-item label="内容匹配" prop="content_pattern">
          <el-input v-model="form.content_pattern" placeholder="如: 账户已成功注册" />
          <div class="form-tip">匹配邮件内容，支持正则表达式</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm" :loading="submitting">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'

const loading = ref(false)
const rules = ref([])
const dialogVisible = ref(false)
const isEditing = ref(false)
const editingId = ref(null)
const submitting = ref(false)
const formRef = ref(null)

const form = ref({
  platform_name: '',
  sender_pattern: '',
  subject_pattern: '',
  content_pattern: ''
})

const formRules = {
  platform_name: [{ required: true, message: '请输入平台名称', trigger: 'blur' }]
}

// 预设规则
const presetRules = [
  { platform: 'MoreLogin', sender: 'morelogin', subject: '注册成功|账户.*注册' },
  { platform: 'AdsPower', sender: 'adspower', subject: '注册成功|welcome' },
  { platform: 'VMLogin', sender: 'vmlogin', subject: '注册|welcome' },
  { platform: 'Multilogin', sender: 'multilogin', subject: '注册|welcome' },
  { platform: 'GoLogin', sender: 'gologin', subject: '注册|welcome' },
  { platform: 'Dolphin', sender: 'dolphin', subject: '注册|welcome' },
  { platform: 'Incogniton', sender: 'incogniton', subject: '注册|welcome' },
  { platform: 'Kameleo', sender: 'kameleo', subject: '注册|welcome' }
]

const fetchRules = async () => {
  loading.value = true
  try {
    const response = await fetch('/api/platform_rules', {
      headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
    })
    if (response.ok) {
      rules.value = await response.json()
    }
  } catch (error) {
    console.error('获取规则失败:', error)
    ElMessage.error('获取规则失败')
  } finally {
    loading.value = false
  }
}

const showAddDialog = () => {
  isEditing.value = false
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

const editRule = (rule) => {
  isEditing.value = true
  editingId.value = rule.id
  form.value = {
    platform_name: rule.platform_name,
    sender_pattern: rule.sender_pattern || '',
    subject_pattern: rule.subject_pattern || '',
    content_pattern: rule.content_pattern || ''
  }
  dialogVisible.value = true
}

const resetForm = () => {
  form.value = {
    platform_name: '',
    sender_pattern: '',
    subject_pattern: '',
    content_pattern: ''
  }
  if (formRef.value) {
    formRef.value.resetFields()
  }
}

const submitForm = async () => {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
  } catch {
    return
  }
  
  // 检查至少有一个匹配规则
  if (!form.value.sender_pattern && !form.value.subject_pattern && !form.value.content_pattern) {
    ElMessage.warning('至少需要设置一个匹配规则')
    return
  }
  
  submitting.value = true
  try {
    const url = isEditing.value ? `/api/platform_rules/${editingId.value}` : '/api/platform_rules'
    const method = isEditing.value ? 'PUT' : 'POST'
    
    const response = await fetch(url, {
      method,
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(form.value)
    })
    
    if (response.ok) {
      ElMessage.success(isEditing.value ? '更新成功' : '添加成功')
      dialogVisible.value = false
      fetchRules()
    } else {
      const data = await response.json()
      ElMessage.error(data.error || '操作失败')
    }
  } catch (error) {
    console.error('操作失败:', error)
    ElMessage.error('操作失败')
  } finally {
    submitting.value = false
  }
}

const toggleRule = async (rule) => {
  try {
    const response = await fetch(`/api/platform_rules/${rule.id}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${localStorage.getItem('token')}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ is_enabled: rule.is_enabled })
    })
    
    if (response.ok) {
      ElMessage.success(rule.is_enabled ? '已启用' : '已禁用')
    } else {
      // 恢复状态
      rule.is_enabled = rule.is_enabled ? 0 : 1
      ElMessage.error('操作失败')
    }
  } catch (error) {
    rule.is_enabled = rule.is_enabled ? 0 : 1
    ElMessage.error('操作失败')
  }
}

const deleteRule = (rule) => {
  ElMessageBox.confirm(`确定要删除规则 "${rule.platform_name}" 吗？`, '确认删除', {
    type: 'warning'
  }).then(async () => {
    try {
      const response = await fetch(`/api/platform_rules/${rule.id}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${localStorage.getItem('token')}` }
      })
      
      if (response.ok) {
        ElMessage.success('删除成功')
        fetchRules()
      } else {
        ElMessage.error('删除失败')
      }
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

const addPresetRule = (preset) => {
  // 检查是否已存在
  const exists = rules.value.some(r => r.platform_name === preset.platform)
  if (exists) {
    ElMessage.warning(`规则 "${preset.platform}" 已存在`)
    return
  }
  
  form.value = {
    platform_name: preset.platform,
    sender_pattern: preset.sender,
    subject_pattern: preset.subject,
    content_pattern: ''
  }
  isEditing.value = false
  editingId.value = null
  dialogVisible.value = true
}

onMounted(() => {
  fetchRules()
})
</script>

<style scoped>
.page-container {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

.rules-container {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.page-title {
  margin: 0;
  font-size: 1.5rem;
}

.text-muted {
  color: #909399;
}

code {
  background: #f5f7fa;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
}

.empty-state {
  padding: 40px 0;
}

.form-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.preset-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
</style>
