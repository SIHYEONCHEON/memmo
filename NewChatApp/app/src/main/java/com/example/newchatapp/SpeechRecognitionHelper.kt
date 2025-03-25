package com.example.newchatapp

import android.util.Log
import kotlinx.coroutines.*

object SpeechRecognitionHelper {

    var onStartRecognition: (() -> Unit)? = null
    var onStopRecognition: (() -> Unit)? = null
    var onResult: ((String) -> Unit)? = null  // 🛠️ 음성 인식 결과 콜백

    fun startSpeechToText() {
        Log.d("SpeechRecognitionTest", "🎤 음성 인식 시작 함수 실행됨")
        CoroutineScope(Dispatchers.Main).launch {
            try {
                onStartRecognition?.invoke() // ✅ 기존 코드 유지
                Log.d("SpeechRecognitionTest", "✅ 음성 인식 onStartRecognition 실행됨")

                // 🎤 실제 음성 인식이 이뤄지는 부분에서 결과를 받아 `onResult`를 실행해야 함
                val recognizedText = "예제 결과 텍스트" // 🛠️ 실제 STT 결과 값으로 변경해야 함
                onResult?.invoke(recognizedText)  // ✅ 기존 코드에 결과 반환 추가

            } catch (e: Exception) {
                Log.e("SpeechRecognitionTest", "❌ STT 시작 오류 발생: ${e.message}")
            }
        }
    }

    fun stopSpeechToText() {
        Log.d("SpeechRecognitionTest", "⏸ 음성 인식 중지 함수 실행됨")
        CoroutineScope(Dispatchers.Main).launch {
            try {
                onStopRecognition?.invoke() // ✅ 기존 코드 유지
                Log.d("SpeechRecognitionTest", "✅ 음성 인식 onStopRecognition 실행됨")

            } catch (e: Exception) {
                Log.e("SpeechRecognitionTest", "❌ STT 중지 오류 발생: ${e.message}")
            }
        }
    }
}
