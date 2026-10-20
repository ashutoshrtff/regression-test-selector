package pages;

import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.support.FindBy;
import org.openqa.selenium.support.PageFactory;

public class CheckoutPage {
    private WebDriver driver;
    public static final String CHECKOUT_URL = "/checkout/payment";
    public static final String PAYMENT_ENDPOINT = "/api/v1/payments/process";

    @FindBy(id = "card-number-input")
    private WebElement cardNumber;

    @FindBy(id = "btn-submit-order")
    private WebElement payButton;

    public CheckoutPage(WebDriver driver) {
        this.driver = driver;
        PageFactory.initElements(driver, this);
    }

    public void navigate() {
        driver.get("https://psp-staging.internal.example.com" + CHECKOUT_URL);
    }

    public void submitOrder() {
        payButton.click();
    }
}
