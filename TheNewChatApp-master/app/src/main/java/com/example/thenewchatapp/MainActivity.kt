/*
 * Project: TheNewChatApp
 * Version: 4.0.0
 * Last updated: 2025-05-30 09:00
 * Author: SiHyeon Cheon
 *
 * [Description]
8필드, 이지커맨드 통합
 */

package com.example.thenewchatapp

import android.content.Intent
import android.content.SharedPreferences
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.*
import androidx.appcompat.app.AppCompatActivity
import androidx.appcompat.app.AppCompatDelegate
import java.io.File
import java.text.SimpleDateFormat
import java.util.*
import android.widget.Toast
import android.widget.PopupMenu

class MainActivity : AppCompatActivity() {

    private lateinit var titleEditText: EditText
    private lateinit var editText: EditText
    private lateinit var backButton: ImageButton
    private lateinit var textViewContent: EditText
    private lateinit var btnVoice: ImageButton
    private lateinit var btnPlus: ImageButton
    private lateinit var fragmentContainer: FrameLayout

    private val customExtension = ".mdocx"
    private var currentFileName: String? = null

    companion object {
        lateinit var prefs: SharedPreferences
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        prefs = getSharedPreferences("settings", MODE_PRIVATE)
        AppCompatDelegate.setDefaultNightMode(
            prefs.getInt("theme_mode", AppCompatDelegate.MODE_NIGHT_FOLLOW_SYSTEM)
        )

        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        textViewContent = findViewById(R.id.textViewContent)
        titleEditText = findViewById(R.id.titleEditText)
        editText = findViewById(R.id.editText)
        backButton = findViewById(R.id.backButton)

        // 챗봇 답변 내용 편집을 메인엑티비티로 변경했을 때 쓰이는 코드
        // EditText 초기화 이후 onCreate 안에 추가
        intent.getStringExtra("originalText")?.let { originalText ->
            editText.setText(originalText)
        }

        val isFromChat = intent.hasExtra("messagePosition")

        backButton.setOnClickListener {
            onBackPressed()  // ✅ 시스템 뒤로가기처럼 자동 저장 후 finish()까지 작동
        }

        val fileName = intent.getStringExtra("fileName")
        if (!fileName.isNullOrEmpty()) {
            val file = File(filesDir, fileName)
            if (file.exists()) {
                val pureTitle = file.name.removeSuffix(customExtension).substringBefore("_")
                if (!pureTitle.startsWith("텍스트 노트 ")) {
                    titleEditText.setText(pureTitle)
                }
                editText.setText(file.readText())
                currentFileName = fileName
            }
        }

        btnVoice = findViewById(R.id.btnVoice)
        btnPlus = findViewById(R.id.btnPlus)
        fragmentContainer = findViewById(R.id.fragmentContainer)

        // ✅ 저장된 텍스트 불러오기 (같은 prefs 사용)
        val savedText = prefs.getString("main_text", "")
        textViewContent.setText(savedText)

        textViewContent.setOnEditorActionListener { v, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                val input = v.text.toString()
                textViewContent.append("\n$input")
                v.setText("")
                true
            } else false
        }

        btnPlus.setOnClickListener {
            PopupMenu(this, it).apply {
                menu.add("챗봇").setOnMenuItemClickListener {
                    startActivity(Intent(this@MainActivity, ChatActivity::class.java))
                    true
                }
                menu.add("필드 화면").setOnMenuItemClickListener {
                    startActivity(Intent(this@MainActivity, FieldActivity::class.java))
                    true
                }
                show()
            }
        }

        btnVoice.setOnClickListener {
            Toast.makeText(
                this,  // Activity 자체를 Context로 사용
                "음성 인식이 시작됩니다.",
                Toast.LENGTH_SHORT
            ).show()
        }
    }

    override fun onBackPressed() {
        saveIfNeeded(forceSave = false)
        super.onBackPressed()
    }

    private fun saveIfNeeded(forceSave: Boolean = false) {
        val content = editText.text.toString().trim()
        if (content.isEmpty() && !forceSave) {
            Toast.makeText(this, "입력한 내용이 없어 저장하지 않았습니다.", Toast.LENGTH_SHORT).show()
            return
        }

        val inputTitle = titleEditText.text.toString().trim()
        val currentTime = Date()

        val saveFileName = when {
            currentFileName != null -> currentFileName!!
            inputTitle.isNotEmpty() -> inputTitle + customExtension
            else -> "텍스트 노트 " + SimpleDateFormat("MMdd_HHmmss", Locale.getDefault()).format(currentTime) + customExtension
        }

        val file = File(filesDir, saveFileName)
        file.writeText(content)
        Toast.makeText(this, "저장되었습니다", Toast.LENGTH_SHORT).show()

        if (currentFileName == null) {
            currentFileName = saveFileName
        }
    }

    override fun onPause() {
        super.onPause()
        prefs.edit().putString("main_text", textViewContent.text.toString()).apply()
    }

    override fun onResume() {
        super.onResume()
        val current = supportFragmentManager.findFragmentById(R.id.editText)
        if (current == null) {
            btnPlus.visibility = View.VISIBLE
            btnVoice.visibility = View.VISIBLE
            textViewContent.visibility = View.VISIBLE
        }
    }

    fun restoreMainUI() {
        textViewContent.visibility = View.VISIBLE
        btnPlus.visibility = View.VISIBLE
        btnVoice.visibility = View.VISIBLE

        fragmentContainer.visibility = View.GONE
    }
}
