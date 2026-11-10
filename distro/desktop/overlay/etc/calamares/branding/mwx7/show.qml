/* What people see while MWX 7 copies itself to the disk: one calm picture and a line of text per slide. */
import QtQuick 2.0;
import calamares.slideshow 1.0;

Presentation {
    id: presentation

    Timer {
        interval: 9000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    Repeater {
        model: [
            { pic: "slide1.jpg", text: "Welcome to MWX 7. Sit back, this takes a few minutes." },
            { pic: "slide2.jpg", text: "Glass windows, a dock and a Start menu: the best of three desktops." },
            { pic: "slide3.jpg", text: "Chrome, Files and Settings are ready the moment you log in." }
        ]
        Slide {
            Image {
                anchors.fill: parent
                source: modelData.pic
                fillMode: Image.PreserveAspectCrop
            }
            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 56
                color: "#b0ffffff"
                Text {
                    anchors.centerIn: parent
                    text: modelData.text
                    color: "#0b2a4d"
                    font.pixelSize: 18
                }
            }
        }
    }

    function onActivate() { }
    function onLeave() { }
}
