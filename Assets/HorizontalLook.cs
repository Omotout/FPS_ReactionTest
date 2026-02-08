using UnityEngine;

public class HorizontalLook : MonoBehaviour
{
    public float mouseSensitivity = 100f;

    void Start()
    {
        Cursor.lockState = CursorLockMode.Locked;
        // 開始時にカメラの角度をリセット
        transform.localRotation = Quaternion.identity;
    }

    void Update()
    {
        float mouseX = Input.GetAxis("Mouse X") * mouseSensitivity * Time.deltaTime;

        // 親オブジェクト（Player）が存在すれば親を回す（一般的なFPSの方式）
        // 親がいなければカメラ自体を回す
        if (transform.parent != null)
        {
            transform.parent.Rotate(Vector3.up * mouseX);
        }
        else
        {
            transform.Rotate(Vector3.up * mouseX);
        }
    }
}