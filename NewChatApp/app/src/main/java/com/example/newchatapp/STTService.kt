package com.example.newchatapp

import android.app.Service
import android.content.Intent
import android.os.*
import android.util.Log
import kotlinx.coroutines.*

class STTService : Service() {

    private val serviceScope = CoroutineScope(Dispatchers.IO)
    private var recognitionJob: Job? = null
    private val handler = Handler(Looper.getMainLooper())  // ✅ 메인 스레드 핸들러

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.getStringExtra("ACTION") ?: ""

        when (action) {
            "START" -> startSpeechRecognition()
            "STOP" -> stopSpeechRecognition()
            "CONFIRM" -> finalizeSpeechRecognition()
        }

        return START_STICKY  // ✅ 강제 종료 후 자동 재시작
    }

    private fun startSpeechRecognition() {
        if (recognitionJob?.isActive == true) {
            Log.d("STTService", "⚠️ 이미 STT 실행 중")
            return
        }

        Log.d("STTService", "🎤 STT 시작됨")

        recognitionJob = serviceScope.launch {
            try {
                handler.post {  // ✅ 무조건 UI 스레드에서 실행되도록 설정
                    SpeechRecognitionHelper.startSpeechToText()
                }
            } catch (e: Exception) {
                Log.e("STTService", "❌ STT 시작 오류 발생: ${e.message}")
                recognitionJob?.cancel()
            }
        }
    }

    private fun stopSpeechRecognition() {
        if (recognitionJob?.isActive == false) {
            Log.d("STTService", "⚠️ STT 실행 중이 아님")
            return
        }

        Log.d("STTService", "🛑 STT 중지됨")

        recognitionJob = serviceScope.launch {
            try {
                handler.post {  // ✅ UI 스레드에서 실행되도록 보장
                    SpeechRecognitionHelper.stopSpeechToText()
                }
                recognitionJob?.cancel()
            } catch (e: Exception) {
                Log.e("STTService", "❌ STT 중지 오류 발생: ${e.message}")
                recognitionJob?.cancel()
            }
        }
    }

    private fun finalizeSpeechRecognition() {
        Log.d("STTService", "🛑 STT 서비스 종료 준비 중...")

        recognitionJob = serviceScope.launch {
            try {
                handler.post {  // ✅ UI 스레드에서 실행되도록 보장
                    SpeechRecognitionHelper.stopSpeechToText()
                }
                delay(500)  // ✅ 안정적인 종료를 위한 대기 시간
                stopSelf()  // ✅ 서비스 종료
            } catch (e: Exception) {
                Log.e("STTService", "❌ STT 종료 오류 발생: ${e.message}")
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.d("STTService", "🛑 STT 서비스 종료됨")

        recognitionJob?.cancel()
        serviceScope.cancel()
        handler.removeCallbacksAndMessages(null)  // ✅ 핸들러 메모리 정리
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
