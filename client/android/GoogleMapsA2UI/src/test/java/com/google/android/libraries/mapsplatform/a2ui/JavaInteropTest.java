// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package com.google.android.libraries.mapsplatform.a2ui;

import static com.google.common.truth.Truth.assertThat;
import static org.junit.Assert.assertThrows;

import android.app.Activity;
import android.widget.FrameLayout;
import java.util.List;
import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.robolectric.Robolectric;
import org.robolectric.RobolectricTestRunner;

/** Java interoperability smoke tests for the public GoogleMapsA2UI Android API. */
@RunWith(RobolectricTestRunner.class)
public final class JavaInteropTest {

  private static final String TEST_API_KEY = "AIzaSyJavaTestKey";
  private Activity activity;

  @Before
  public void setUp() {
    activity = Robolectric.buildActivity(Activity.class).setup().get();
  }

  @Test
  public void services_provideAndGetApiKeyFromJava() {
    A2UIServices.provideApiKey(TEST_API_KEY);
    assertThat(A2UIServices.getApiKey()).isEqualTo(TEST_API_KEY);
    assertThrows(IllegalArgumentException.class, () -> A2UIServices.provideApiKey(""));
    assertThrows(IllegalStateException.class, () -> A2UIServices.provideApiKey("DifferentKey"));
  }

  @Test
  public void parser_parseAndExceptionsFromJava() throws A2AParserException {
    String responseJson =
        "{\"parts\":[{\"text\":\"Hello\"},{\"data\":{\"createSurface\":{\"surfaceId\":\"s1\"}}}]}";
    List<ParsedA2AEvent> events = A2AResponseParser.parse(responseJson);

    assertThat(events).hasSize(2);
    assertThat(events.get(0)).isInstanceOf(ParsedA2AEvent.Text.class);
    assertThat(((ParsedA2AEvent.Text) events.get(0)).getText()).isEqualTo("Hello");

    assertThat(events.get(1)).isInstanceOf(ParsedA2AEvent.Data.class);
    ParsedA2AEvent.Data dataEvent = (ParsedA2AEvent.Data) events.get(1);
    assertThat(dataEvent.getMetadata()).isNotNull();
    assertThat(dataEvent.getMetadata().getMimeType()).isEqualTo("application/json+a2ui");

    assertThrows(A2AParserException.InvalidJsonFormat.class, () -> A2AResponseParser.parse("{bad"));
    assertThrows(
        A2AParserException.InvalidPayloadStructure.class,
        () -> A2AResponseParser.parse("{\"status\":\"ok\"}"));
    A2AParserException.ServerError serverError =
        assertThrows(
            A2AParserException.ServerError.class,
            () ->
                A2AResponseParser.parse(
                    "{\"error\":{\"code\":-32000,\"message\":\"Server failure\"}}"));
    assertThat(serverError.getCode()).isEqualTo(-32000);
  }

  @Test
  public void models_overloadedConstructorsFromJava() {
    ParsedA2AEventMetadata emptyMetadata = new ParsedA2AEventMetadata();
    assertThat(emptyMetadata.getMimeType()).isNull();

    ParsedA2AEvent.Data dataWithoutMetadata = new ParsedA2AEvent.Data("[]");
    assertThat(dataWithoutMetadata.getMetadata()).isNull();
  }

  @Test
  public void view_constructConfigureListenersAndRenderFromJava() {
    A2UIServices.provideApiKey(TEST_API_KEY);
    A2UIView view = new A2UIView(activity);
    assertThat(view).isInstanceOf(FrameLayout.class);

    view.setOnRenderCompleteListener(latencyMs -> {});
    view.setOnUserActionListener(actionJson -> {});

    assertThat(view.getOnRenderCompleteListener()).isNotNull();
    assertThat(view.getOnUserActionListener()).isNotNull();

    view.render("[{\"createSurface\":{\"surfaceId\":\"java-test\"}}]");
    view.updateA2uiJson("[{\"updateComponents\":{\"surfaceId\":\"java-test\",\"components\":[]}}]");
  }
}
